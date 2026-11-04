"""
Genera test/esempio-dati.json: un Project INVENTATO, nel formato che
restituisce GitHub, per provare il cruscotto senza collegarsi.

    python3 gestione/test/genera_esempio.py
"""

import json
from pathlib import Path

ORG = "Git-Push-Team"
contatore = 0


def nuovo_id(prefisso: str) -> str:
    global contatore
    contatore += 1
    return f"{prefisso}_{contatore}"


def commento(login, corpo, quando, bot=False):
    return {"id": nuovo_id("IC"), "url": f"https://github.com/{ORG}/x#c{contatore}", "body": corpo,
            "createdAt": quando, "author": {"login": login, "__typename": "Bot" if bot else "User"}}


def campi(ruolo=None, stimate=None, sprint=None, stato=None):
    nodi = []
    if ruolo:
        nodi.append({"__typename": "ProjectV2ItemFieldSingleSelectValue", "name": ruolo, "field": {"name": "Ruolo"}})
    if stimate is not None:
        nodi.append({"__typename": "ProjectV2ItemFieldNumberValue", "number": stimate, "field": {"name": "Ore stimate"}})
    if sprint:
        nodi.append({"__typename": "ProjectV2ItemFieldIterationValue", "title": "Sprint", "startDate": sprint,
                     "duration": 14, "field": {"name": "Sprint"}})
    if stato:
        nodi.append({"__typename": "ProjectV2ItemFieldSingleSelectValue", "name": stato, "field": {"name": "Status"}})
    return {"nodes": nodi}


def issue(repo, numero, titolo, commenti, chiusa_il=None, assegnati=(), pr=(), **kw):
    return {"id": nuovo_id("PVTI"), "fieldValues": campi(**kw), "content": {
        "__typename": "Issue", "id": nuovo_id("I"), "number": numero, "title": titolo,
        "url": f"https://github.com/{ORG}/{repo}/issues/{numero}",
        "state": "CLOSED" if chiusa_il else "OPEN", "closedAt": chiusa_il,
        "repository": {"nameWithOwner": f"{ORG}/{repo}"},
        "assignees": {"nodes": [{"login": a} for a in assegnati]},
        "comments": {"nodes": commenti},
        "closedByPullRequestsReferences": {"nodes": list(pr)}}}


def pr_collegata(repo, numero, commenti):
    return {"id": nuovo_id("PR"), "number": numero, "url": f"https://github.com/{ORG}/{repo}/pull/{numero}",
            "repository": {"nameWithOwner": f"{ORG}/{repo}"}, "comments": {"nodes": commenti}}


verifica_75 = commento("itsluca57", "Verificata, tutto ok.\n/ore 1 verificatore", "2026-11-11T18:00:00Z")

elementi = [
    issue("docs", 70, "Norme di Progetto: prima stesura", [
        commento("firestone109", "Fatta la struttura.\n/ore 2\n/ore 1,5 2026-11-04", "2026-11-05T19:00:00Z"),
        commento("firestone109", "/ore 2h amministratore", "2026-11-10T20:00:00Z"),
        commento("firestone109", "Esempio per gli altri:\n```\n/ore 99\n```", "2026-11-10T20:05:00Z"),
        commento("git-push-team-gestione", "<!-- riepilogo-ore -->\n/ore 2", "2026-11-10T20:06:00Z", bot=True),
    ], chiusa_il="2026-11-12T10:00:00Z", assegnati=["firestone109"],
        pr=[pr_collegata("docs", 75, [verifica_75])],
        ruolo="Amministratore", stimate=6, sprint="2026-11-02", stato="Done"),
    issue("docs", 71, "Piano di Progetto: struttura", [
        commento("gaexxx", "/ore 3", "2026-11-06T17:00:00Z"),
        commento("gaexxx", "/ore abc", "2026-11-06T17:01:00Z"),
        commento("sconosciuto", "/ore 5", "2026-11-06T17:02:00Z"),
    ], assegnati=["gaexxx"], ruolo="Responsabile", stimate=4, sprint="2026-11-02", stato="In review"),
    issue("docs", 72, "Piano di Progetto: analisi dei rischi", [
        commento("MaZzU05", "/ore 4 progettista\n/ore 1 programmatore", "2026-11-07T10:00:00Z"),
    ], chiusa_il="2026-11-08T10:00:00Z", assegnati=["MaZzU05"], ruolo="Progettista", stimate=4,
        sprint="2026-11-02", stato="Done"),
    issue("docs", 73, "Correggere refusi nel Glossario", [],
          chiusa_il="2026-11-09T10:00:00Z", assegnati=["enricobiasini"], sprint="2026-11-02", stato="Done"),
    issue("docs", 74, "Riunione interna 2026-11-09", [
        commento(u, "/ore 1", "2026-11-09T21:30:00Z")
        for u in ["enricobiasini", "itsluca57", "alec0r", "firestone109", "MaZzU05", "gaexxx"]
    ], chiusa_il="2026-11-10T10:00:00Z", sprint="2026-11-02", stato="Done"),
    issue("docs", 80, "Analisi dei Requisiti: casi d'uso principali", [
        commento("enricobiasini", "/ore 2 verificatore", "2026-11-17T18:00:00Z"),
        commento("enricobiasini", "/ore 3 analista 2026-11-18", "2026-11-19T18:00:00Z"),
        commento("itsluca57", "/ore 2,5", "2026-11-18T18:00:00Z"),
    ], assegnati=["itsluca57"], ruolo="Analista", stimate=8, sprint="2026-11-16", stato="In Progress"),
    issue("poc", 3, "PoC: primo prototipo con RubyLLM", [
        commento("alec0r", "/ore 1 responsabile", "2026-11-17T09:00:00Z"),
        commento("gaexxx", "/ore 2 progettista\n/ore 1h30 progettista", "2026-11-18T09:00:00Z"),
    ], assegnati=["gaexxx"], ruolo="Progettista", stimate=6, sprint="2026-11-16", stato="In Progress"),
    # la PR docs#75 è anche un elemento del Project: il suo commento non va contato due volte
    {"id": "PVTI_pr75", "fieldValues": campi(stato="Done"), "content": {
        "__typename": "PullRequest", "id": "PR_75", "number": 75, "title": "Norme: prima stesura",
        "url": f"https://github.com/{ORG}/docs/pull/75", "state": "MERGED", "closedAt": "2026-11-12T10:00:00Z",
        "repository": {"nameWithOwner": f"{ORG}/docs"}, "assignees": {"nodes": []},
        "comments": {"nodes": [verifica_75]},
        "closingIssuesReferences": {"nodes": [{"number": 70, "repository": {"nameWithOwner": f"{ORG}/docs"}}]}}},
    {"id": "PVTI_bozza", "fieldValues": campi(), "content": {"__typename": "DraftIssue", "title": "Idea da valutare"}},
]

dati = {"titolo": "GIT PUSH TEAM", "elementi": elementi, "letto_il": "2026-11-20T03:00:00+01:00"}
destinazione = Path(__file__).with_name("esempio-dati.json")
destinazione.write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"Scritto {destinazione}")
