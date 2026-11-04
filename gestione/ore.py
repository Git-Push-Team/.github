"""
ore.py -- gestisce i comandi /ore. Lo lancia il workflow "Ore" quando
qualcuno scrive, modifica o cancella un commento con /ore.

Cosa fa, per la issue a cui il commento si riferisce:
  1. rilegge TUTTI i comandi /ore della issue e delle PR che la chiudono
     (così modificare o cancellare un commento corregge i totali);
  2. scrive il totale nel campo "Ore effettive" del Project (aggiungendo la
     issue al Project se non c'è);
  3. aggiorna un unico commento di riepilogo: ore per persona e ruolo,
     dettaglio, comandi non validi;
  4. mette una reazione al commento: 👍 se è valido, 😕 se c'è un errore.

Un commento su una PR vale per la issue che la PR chiude ("Closes #12").
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

from bacheca import carica_project, elemento, imposta_numero
from comune import (COMMENTI, Configurazione, ErroreGitHub, GitHub, avviso,
                    carica_configurazione, ore_testo, riferimento, tutti_i_commenti)
from registro_ore import MARCATORE, Scarto, Voce, righe_di_comando, voci_da_commenti

DATI_ELEMENTO = """
  id number title url
  repository { nameWithOwner }
  %s
  projectItems(first: 20) { nodes { id project { id } } }
""" % COMMENTI

QUERY = """
query($proprietario: String!, $nome: String!, $numero: Int!, $dopo_commenti: String) {
  repository(owner: $proprietario, name: $nome) {
    issueOrPullRequest(number: $numero) {
      __typename
      ... on Issue {
        %s
        closedByPullRequestsReferences(first: 10, includeClosedPrs: true) {
          nodes { id number url repository { nameWithOwner } %s }
        }
      }
      ... on PullRequest {
        %s
        closingIssuesReferences(first: 10) {
          nodes { number repository { nameWithOwner } }
        }
      }
    }
  }
}""" % (DATI_ELEMENTO, COMMENTI, DATI_ELEMENTO)


def leggi(gh: GitHub, repo_completo: str, numero: int) -> dict:
    proprietario, nome = repo_completo.split("/", 1)
    dati = gh.query(QUERY, proprietario=proprietario, nome=nome, numero=numero)
    nodo = ((dati.get("repository") or {}).get("issueOrPullRequest"))
    if not nodo:
        raise ErroreGitHub(f"{repo_completo}#{numero} non trovata")
    return nodo


def raccogli(gh: GitHub, issue: dict, conf: Configurazione) -> tuple[list[Voce], list[Scarto]]:
    """Le voci di una issue (o PR) e delle PR che la chiudono."""
    org = conf.organizzazione
    fonte = riferimento(issue["repository"]["nameWithOwner"], issue["number"], org)
    voci, scarti = voci_da_commenti(tutti_i_commenti(gh, issue), fonte, conf)
    for pr in (issue.get("closedByPullRequestsReferences") or {}).get("nodes") or []:
        fonte_pr = riferimento(pr["repository"]["nameWithOwner"], pr["number"], org)
        v, s = voci_da_commenti(tutti_i_commenti(gh, pr), fonte_pr, conf)
        voci += v
        scarti += s
    return voci, scarti


def riepilogo(voci: list[Voce], scarti: list[Scarto], conf: Configurazione, nota: str = "") -> str:
    """Il testo del commento di riepilogo."""
    totale = sum(v.ore for v in voci)
    righe = [MARCATORE, f"### ⏱️ Ore registrate: {ore_testo(totale)}", ""]
    if nota:
        righe += [nota, ""]
    if voci:
        per_persona = defaultdict(float)
        for v in voci:
            per_persona[(v.persona, v.ruolo)] += v.ore
        righe += ["| Persona | Ruolo | Ore |", "| --- | --- | ---: |"]
        for (persona, ruolo), ore in sorted(per_persona.items(),
                                            key=lambda x: (conf.membri[x[0][0]].nome, x[0][1])):
            righe.append(f"| {conf.membri[persona].nome} | {ruolo} | {ore_testo(ore)} |")
        righe += ["", f"<details><summary>Dettaglio ({len(voci)} registrazioni)</summary>", "",
                  "| Data | Persona | Ruolo | Ore | Sprint | Dove |",
                  "| --- | --- | --- | ---: | --- | --- |"]
        for v in sorted(voci, key=lambda v: (v.giorno, v.persona)):
            sprint = f"{v.sprint}" if v.sprint else "—"
            segno = " ⚑" if v.fuori_piano else ""
            righe.append(f"| {v.giorno.isoformat()} | {conf.membri[v.persona].nome} | {v.ruolo}{segno} "
                         f"| {ore_testo(v.ore)} | {sprint} | [{v.fonte}]({v.url}) |")
        righe += ["", "</details>", ""]
        if any(v.fuori_piano for v in voci):
            righe += ["⚑ = ruolo non pianificato per quella persona in quello sprint (le ore contano "
                      "lo stesso; il cruscotto le segnala).", ""]
    if scarti:
        righe += ["⚠️ **Comandi non validi**, non contati. Correggete (o cancellate) il commento: "
                  "il riepilogo si aggiorna da solo.", ""]
        for s in scarti:
            chi = f"@{s.autore}" if conf.membro_da_github(s.autore) else f"`{s.autore}`"
            righe.append(f"- {chi}, [{s.fonte}]({s.url}): `{s.riga}` → {s.motivo}")
        righe.append("")
    righe.append("<sub>Come si segnano le ore: un commento con <code>/ore 2</code>, "
                 "<code>/ore 1,5 verificatore</code> o <code>/ore 1h30 analista 2026-11-05</code>. "
                 "Una riga per comando; le ore sono di chi scrive il commento.</sub>")
    return "\n".join(righe)


def aggiorna_riepilogo(gh: GitHub, nodo: dict, testo: str, crea: bool = True) -> None:
    """Aggiorna il commento di riepilogo; se non c'è lo crea (solo se crea=True)."""
    esistente = next((c for c in tutti_i_commenti(gh, nodo)
                      if MARCATORE in (c.get("body") or "")
                      and (c.get("author") or {}).get("__typename") == "Bot"), None)
    if esistente:
        if esistente["body"].strip() != testo.strip():
            gh.query("""mutation($id: ID!, $corpo: String!) {
                          updateIssueComment(input: {id: $id, body: $corpo}) { issueComment { id } }
                        }""", id=esistente["id"], corpo=testo)
    elif crea:
        gh.query("""mutation($id: ID!, $corpo: String!) {
                      addComment(input: {subjectId: $id, body: $corpo}) { commentEdge { node { id } } }
                    }""", id=nodo["id"], corpo=testo)


def reagisci(gh: GitHub, id_commento: str, valido: bool) -> None:
    """👍 se il commento è valido, 😕 se ha errori (e toglie l'altra reazione)."""
    metti, togli = ("THUMBS_UP", "CONFUSED") if valido else ("CONFUSED", "THUMBS_UP")
    gh.query("""mutation($id: ID!, $r: ReactionContent!) {
                  addReaction(input: {subjectId: $id, content: $r}) { reaction { content } }
                }""", id=id_commento, r=metti)
    try:
        gh.query("""mutation($id: ID!, $r: ReactionContent!) {
                      removeReaction(input: {subjectId: $id, content: $r}) { reaction { content } }
                    }""", id=id_commento, r=togli)
    except ErroreGitHub:
        pass


def gestisci(gh: GitHub, conf: Configurazione, evento: dict) -> None:
    repo = evento["repository"]["full_name"]
    numero = evento["issue"]["number"]
    commento = evento.get("comment") or {}
    nodo = leggi(gh, repo, numero)

    # su quali issue ricalcolare: la issue stessa, oppure quelle chiuse dalla PR
    nota = ""
    if nodo["__typename"] == "PullRequest":
        collegate = (nodo.get("closingIssuesReferences") or {}).get("nodes") or []
        destinazioni = [leggi(gh, i["repository"]["nameWithOwner"], i["number"]) for i in collegate]
        if not destinazioni:
            destinazioni = [nodo]
            nota = ("ℹ️ Questa PR non chiude nessuna issue: le ore restano qui. Scrivete "
                    "`Closes #numero` nella descrizione perché vadano alla issue.")
    else:
        destinazioni = [nodo]

    project = carica_project(gh, conf)
    for destinazione in destinazioni:
        voci, scarti = raccogli(gh, destinazione, conf)
        if destinazione["__typename"] == "PullRequest" and not conf.campi.get("aggiungi_pr_al_project"):
            item = elemento(gh, project, destinazione, aggiungi=False)
        else:
            item = elemento(gh, project, destinazione, aggiungi=True)
        if item:
            imposta_numero(gh, project, item, conf.campo("ore_effettive"), sum(v.ore for v in voci))
        # il riepilogo si crea alla prima ora registrata e poi si aggiorna sempre,
        # anche quando tutti i comandi vengono cancellati (torna a 0)
        aggiorna_riepilogo(gh, destinazione, riepilogo(voci, scarti, conf, nota),
                           crea=bool(voci or scarti or nota))
        print(f"{riferimento(destinazione['repository']['nameWithOwner'], destinazione['number'], conf.organizzazione)}: "
              f"{len(voci)} registrazioni, {ore_testo(sum(v.ore for v in voci))} ore, {len(scarti)} non valide")

    # reazione al commento appena scritto o modificato
    if evento.get("action") in ("created", "edited") and commento.get("node_id"):
        righe = righe_di_comando(commento.get("body") or "")
        if righe:
            fonte = riferimento(repo, numero, conf.organizzazione)
            finto = {"id": commento["node_id"], "url": commento.get("html_url", ""),
                     "body": commento.get("body", ""), "createdAt": commento["created_at"],
                     "author": {"login": (commento.get("user") or {}).get("login"),
                                "__typename": "Bot" if (commento.get("user") or {}).get("type") == "Bot" else "User"}}
            _, errori = voci_da_commenti([finto], fonte, conf)
            reagisci(gh, commento["node_id"], valido=not errori)


def main() -> int:
    conf = carica_configurazione()
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        evento = json.load(f)
    try:
        gestisci(GitHub(), conf, evento)
    except ErroreGitHub as errore:
        avviso(f"Errore con GitHub: {errore}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())