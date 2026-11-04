"""
dati.py -- legge dal GitHub Project tutto ciò che serve al cruscotto:
le attività (issue e PR) con i loro campi e tutte le ore registrate con /ore.

I dati letti si possono salvare in un file JSON (--salva-dati) e rileggere
(--da-file): serve per provare il cruscotto senza collegarsi a GitHub.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from comune import COMMENTI, Configurazione, GitHub, ErroreGitHub, normalizza, riferimento, tutti_i_commenti
from registro_ore import Scarto, Voce, voci_da_commenti

QUERY_ELEMENTI = """
query($org: String!, $numero: Int!, $dopo: String, $dopo_commenti: String) {
  organization(login: $org) {
    projectV2(number: $numero) {
      title
      items(first: 40, after: $dopo) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          fieldValues(first: 30) {
            nodes {
              __typename
              ... on ProjectV2ItemFieldNumberValue { number field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldSingleSelectValue { name field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldIterationValue { title startDate duration field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldTextValue { text field { ... on ProjectV2FieldCommon { name } } }
              ... on ProjectV2ItemFieldDateValue { date field { ... on ProjectV2FieldCommon { name } } }
            }
          }
          content {
            __typename
            ... on DraftIssue { title }
            ... on Issue {
              id number title url state closedAt
              repository { nameWithOwner }
              assignees(first: 10) { nodes { login } }
              %s
              closedByPullRequestsReferences(first: 5, includeClosedPrs: true) {
                nodes { id number url repository { nameWithOwner } %s }
              }
            }
            ... on PullRequest {
              id number title url state closedAt
              repository { nameWithOwner }
              assignees(first: 10) { nodes { login } }
              %s
              closingIssuesReferences(first: 5) { nodes { number repository { nameWithOwner } } }
            }
          }
        }
      }
    }
  }
}""" % (COMMENTI, COMMENTI, COMMENTI)


@dataclass
class Attivita:
    rif: str                     # "docs#12"
    titolo: str
    url: str
    tipo: str                    # Issue, PullRequest, DraftIssue
    chiusa: bool
    chiusa_il: date | None
    assegnatari: list[str]       # chiavi dei membri
    ruolo: str | None            # campo Ruolo del Project
    ore_stimate: float | None
    sprint_inizio: date | None   # inizio dell'iterazione del campo Sprint
    colonna: str | None          # campo Status
    voci: list[Voce] = field(default_factory=list)


@dataclass
class DatiProject:
    titolo: str
    attivita: list[Attivita]
    voci: list[Voce]             # tutte, senza doppioni
    scarti: list[Scarto]


def _valori_campi(nodo: dict) -> dict[str, dict]:
    valori = {}
    for v in (nodo.get("fieldValues") or {}).get("nodes") or []:
        nome = ((v or {}).get("field") or {}).get("name")
        if nome:
            valori[normalizza(nome)] = v
    return valori


def leggi_grezzi(gh: GitHub, conf: Configurazione) -> dict:
    """I dati così come arrivano da GitHub (con tutte le pagine di commenti)."""
    elementi, dopo, titolo = [], None, ""
    while True:
        dati = gh.query(QUERY_ELEMENTI, org=conf.organizzazione, numero=conf.numero_project, dopo=dopo)
        project = (dati.get("organization") or {}).get("projectV2")
        if not project:
            raise ErroreGitHub(f"Project n. {conf.numero_project} non trovato")
        titolo = project["title"]
        blocco = project["items"]
        for nodo in blocco["nodes"]:
            contenuto = nodo.get("content") or {}
            if contenuto.get("__typename") in ("Issue", "PullRequest"):
                contenuto["comments"] = {"nodes": tutti_i_commenti(gh, contenuto)}
                for pr in (contenuto.get("closedByPullRequestsReferences") or {}).get("nodes") or []:
                    pr["comments"] = {"nodes": tutti_i_commenti(gh, pr)}
            elementi.append(nodo)
        if not blocco["pageInfo"]["hasNextPage"]:
            break
        dopo = blocco["pageInfo"]["endCursor"]
    return {"titolo": titolo, "elementi": elementi, "letto_il": datetime.now(conf.fuso).isoformat()}


def interpreta_grezzi(grezzi: dict, conf: Configurazione) -> DatiProject:
    org = conf.organizzazione
    attivita, tutte_voci, scarti, visti = [], [], [], set()

    def aggiungi(voci_nuove: list[Voce], scarti_nuovi: list[Scarto], dove: Attivita) -> None:
        # lo stesso commento può arrivare due volte (dalla PR e dalla issue che
        # chiude): conta una volta sola, ma tutte le sue righe /ore
        nuove = [v for v in voci_nuove if v.commento not in visti]
        visti.update(v.commento for v in voci_nuove)
        dove.voci.extend(nuove)
        tutte_voci.extend(nuove)
        for s in scarti_nuovi:
            if (s.url, s.riga) not in {(x.url, x.riga) for x in scarti}:
                scarti.append(s)

    # prima le issue: le ore scritte sulle PR vanno alla issue che chiudono
    elementi = sorted(grezzi["elementi"],
                      key=lambda n: (n.get("content") or {}).get("__typename") != "Issue")
    for nodo in elementi:
        c = nodo.get("content") or {}
        valori = _valori_campi(nodo)
        tipo = c.get("__typename", "DraftIssue")
        if tipo == "DraftIssue":
            rif, url, chiusa, chiusa_il = "bozza", "", False, None
        else:
            rif = riferimento(c["repository"]["nameWithOwner"], c["number"], org)
            url = c["url"]
            chiusa = c["state"] in ("CLOSED", "MERGED")
            chiusa_il = (datetime.fromisoformat(c["closedAt"].replace("Z", "+00:00"))
                         .astimezone(conf.fuso).date() if c.get("closedAt") else None)
        ore_stimate = (valori.get(normalizza(conf.campo("ore_stimate"))) or {}).get("number")
        sprint = (valori.get(normalizza(conf.campo("sprint"))) or {}).get("startDate")
        assegnatari = []
        for a in (c.get("assignees") or {}).get("nodes") or []:
            m = conf.membro_da_github(a.get("login"))
            if m:
                assegnatari.append(m.chiave)
        a = Attivita(
            rif=rif, titolo=c.get("title", ""), url=url, tipo=tipo, chiusa=chiusa, chiusa_il=chiusa_il,
            assegnatari=assegnatari,
            ruolo=(valori.get(normalizza(conf.campo("ruolo"))) or {}).get("name"),
            ore_stimate=float(ore_stimate) if ore_stimate is not None else None,
            sprint_inizio=date.fromisoformat(sprint) if sprint else None,
            colonna=(valori.get(normalizza(conf.campo("stato"))) or {}).get("name"),
        )
        if tipo != "DraftIssue":
            aggiungi(*voci_da_commenti(c["comments"]["nodes"], rif, conf), a)
            for pr in (c.get("closedByPullRequestsReferences") or {}).get("nodes") or []:
                rif_pr = riferimento(pr["repository"]["nameWithOwner"], pr["number"], org)
                aggiungi(*voci_da_commenti(pr["comments"]["nodes"], rif_pr, conf), a)
        attivita.append(a)
    return DatiProject(grezzi.get("titolo", ""), attivita, tutte_voci, scarti)


def leggi(conf: Configurazione, gh: GitHub | None = None, da_file: Path | None = None,
          salva_in: Path | None = None) -> DatiProject:
    if da_file:
        grezzi = json.loads(Path(da_file).read_text(encoding="utf-8"))
    else:
        grezzi = leggi_grezzi(gh or GitHub(), conf)
    if salva_in:
        Path(salva_in).parent.mkdir(parents=True, exist_ok=True)
        Path(salva_in).write_text(json.dumps(grezzi, ensure_ascii=False, indent=1), encoding="utf-8")
    return interpreta_grezzi(grezzi, conf)
