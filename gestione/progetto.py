"""
progetto.py -- collega issue e PR al GitHub Project. Lo lancia il workflow
"Project" a ogni issue aperta e a ogni PR aperta.

  - issue aperta (o riaperta): la aggiunge al Project; alla prima apertura
    compila Ruolo e Ore stimate leggendoli dal modulo della issue e, se
    richiesto in pianificazione.toml, la mette nello sprint in corso;
  - PR aperta o pronta per la revisione: le issue che chiude ("Closes #12")
    passano nella colonna di revisione (es. "In review").

Quando la PR viene unita, la issue si chiude e va in "Done" da sola, con i
workflow già presenti nel Project (vedi README, passo 3).
"""

from __future__ import annotations

import json
import os
import re
import sys

from bacheca import carica_project, elemento, imposta_iterazione, imposta_numero, imposta_opzione
from comune import (Configurazione, ErroreGitHub, GitHub, avviso, carica_configurazione,
                    ruolo_da_testo)

ELEMENTO = "id number title projectItems(first: 20) { nodes { id project { id } } }"


def sezione_modulo(corpo: str, titolo: str) -> str | None:
    """Il valore di un campo dei moduli delle issue: '### Ruolo\\n\\nAnalista'."""
    m = re.search(r"^###\s+" + re.escape(titolo) + r"\s*\n+(.*?)(?=\n###\s|\Z)", corpo or "",
                  re.MULTILINE | re.DOTALL)
    if not m:
        return None
    valore = m.group(1).strip()
    return None if not valore or valore == "_No response_" else valore


def ore_da_testo(testo: str | None) -> float | None:
    if not testo:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", testo)
    return float(m.group(0).replace(",", ".")) if m else None


def issue_aperta(gh: GitHub, conf: Configurazione, evento: dict) -> None:
    issue = evento["issue"]
    dati = gh.query("query($id: ID!) { node(id: $id) { ... on Issue { %s } } }" % ELEMENTO,
                    id=issue["node_id"])
    project = carica_project(gh, conf)
    item = elemento(gh, project, dati["node"], aggiungi=True)
    if evento["action"] != "opened":
        return
    corpo = issue.get("body") or ""
    ruolo = ruolo_da_testo(sezione_modulo(corpo, "Ruolo") or "")
    if ruolo:
        imposta_opzione(gh, project, item, conf.campo("ruolo"), ruolo)
    stima = ore_da_testo(sezione_modulo(corpo, "Stima in ore"))
    if stima is not None:
        imposta_numero(gh, project, item, conf.campo("ore_stimate"), stima)
    if conf.campi.get("assegna_sprint_corrente", True):
        imposta_iterazione(gh, project, item, conf.campo("sprint"), conf.oggi())
    print(f"#{issue['number']} nel Project: ruolo={ruolo}, stima={stima}")


def pr_aperta(gh: GitHub, conf: Configurazione, evento: dict) -> None:
    pr = evento["pull_request"]
    if pr.get("draft"):
        print("PR in bozza: non sposto nulla")
        return
    dati = gh.query("""
        query($id: ID!) {
          node(id: $id) {
            ... on PullRequest {
              %s
              closingIssuesReferences(first: 10) { nodes { %s } }
            }
          }
        }""" % (ELEMENTO, ELEMENTO), id=pr["node_id"])
    nodo = dati["node"]
    project = carica_project(gh, conf)
    if conf.campi.get("aggiungi_pr_al_project"):
        elemento(gh, project, nodo, aggiungi=True)
    colonna = conf.campo("stato_in_revisione")
    collegate = (nodo.get("closingIssuesReferences") or {}).get("nodes") or []
    if not collegate:
        avviso(f"La PR #{pr['number']} non chiude nessuna issue: scrivete \"Closes #numero\" nella descrizione")
    for issue in collegate:
        item = elemento(gh, project, issue, aggiungi=True)
        if imposta_opzione(gh, project, item, conf.campo("stato"), colonna):
            print(f"#{issue['number']} -> {colonna}")


def main() -> int:
    conf = carica_configurazione()
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        evento = json.load(f)
    nome_evento = os.environ.get("GITHUB_EVENT_NAME", "")
    try:
        if nome_evento == "issues":
            issue_aperta(GitHub(), conf, evento)
        elif nome_evento in ("pull_request", "pull_request_target"):
            pr_aperta(GitHub(), conf, evento)
        else:
            print(f"Evento {nome_evento}: niente da fare")
    except ErroreGitHub as errore:
        avviso(f"Errore con GitHub: {errore}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
