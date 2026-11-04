"""
bacheca.py -- lettura e scrittura dei campi del GitHub Project.

Lo usano ore.py (scrive "Ore effettive") e progetto.py (aggiunge le issue,
compila Ruolo, Ore stimate e Sprint, sposta la issue "In review").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from comune import Configurazione, GitHub, ErroreGitHub, avviso, normalizza


@dataclass
class Campo:
    id: str
    nome: str
    tipo: str                                   # NUMBER, SINGLE_SELECT, ITERATION, TEXT, DATE...
    opzioni: dict[str, str] = field(default_factory=dict)          # nome normalizzato -> id
    iterazioni: list[dict] = field(default_factory=list)           # id, title, startDate, duration


@dataclass
class Project:
    id: str
    titolo: str
    campi: dict[str, Campo]                     # nome normalizzato -> Campo

    def campo(self, nome: str) -> Campo | None:
        return self.campi.get(normalizza(nome)) if nome else None


def carica_project(gh: GitHub, conf: Configurazione) -> Project:
    dati = gh.query("""
        query($org: String!, $numero: Int!) {
          organization(login: $org) {
            projectV2(number: $numero) {
              id title
              fields(first: 50) {
                nodes {
                  __typename
                  ... on ProjectV2Field { id name dataType }
                  ... on ProjectV2SingleSelectField { id name dataType options { id name } }
                  ... on ProjectV2IterationField {
                    id name dataType
                    configuration {
                      iterations { id title startDate duration }
                      completedIterations { id title startDate duration }
                    }
                  }
                }
              }
            }
          }
        }""", org=conf.organizzazione, numero=conf.numero_project)
    p = (dati.get("organization") or {}).get("projectV2")
    if not p:
        raise ErroreGitHub(f"Project n. {conf.numero_project} di {conf.organizzazione} non trovato "
                           "(la GitHub App ha il permesso Projects?)")
    campi = {}
    for nodo in p["fields"]["nodes"]:
        if not nodo or "id" not in nodo:
            continue
        campo = Campo(nodo["id"], nodo["name"], nodo.get("dataType", ""))
        for o in nodo.get("options") or []:
            campo.opzioni[normalizza(o["name"])] = o["id"]
        conf_it = nodo.get("configuration") or {}
        campo.iterazioni = (conf_it.get("iterations") or []) + (conf_it.get("completedIterations") or [])
        campi[normalizza(nodo["name"])] = campo
    return Project(p["id"], p["title"], campi)


def iterazione_del_giorno(campo: Campo, giorno: date) -> dict | None:
    for it in campo.iterazioni:
        inizio = date.fromisoformat(it["startDate"])
        if inizio <= giorno < inizio + timedelta(days=int(it["duration"])):
            return it
    return None


def elemento(gh: GitHub, project: Project, contenuto: dict, aggiungi: bool = True) -> str | None:
    """L'id dell'elemento del Project per una issue/PR (contenuto con 'id' e
    'projectItems'); se non c'è e aggiungi=True, la aggiunge al Project."""
    for nodo in (contenuto.get("projectItems") or {}).get("nodes") or []:
        if (nodo.get("project") or {}).get("id") == project.id:
            return nodo["id"]
    if not aggiungi:
        return None
    dati = gh.query("""
        mutation($p: ID!, $c: ID!) {
          addProjectV2ItemById(input: {projectId: $p, contentId: $c}) { item { id } }
        }""", p=project.id, c=contenuto["id"])
    return dati["addProjectV2ItemById"]["item"]["id"]


def _imposta(gh: GitHub, project: Project, item: str, campo: Campo, valore: dict) -> None:
    gh.query("""
        mutation($p: ID!, $i: ID!, $f: ID!, $v: ProjectV2FieldValue!) {
          updateProjectV2ItemFieldValue(input: {projectId: $p, itemId: $i, fieldId: $f, value: $v}) {
            projectV2Item { id }
          }
        }""", p=project.id, i=item, f=campo.id, v=valore)


def imposta_numero(gh: GitHub, project: Project, item: str, nome: str, valore: float) -> bool:
    campo = project.campo(nome)
    if campo is None or campo.tipo != "NUMBER":
        avviso(f"Nel Project manca il campo numerico \"{nome}\" (vedi pianificazione.toml, [campi])")
        return False
    _imposta(gh, project, item, campo, {"number": float(valore)})
    return True


def imposta_opzione(gh: GitHub, project: Project, item: str, nome: str, opzione: str) -> bool:
    campo = project.campo(nome)
    if campo is None or not campo.opzioni:
        avviso(f"Nel Project manca il campo a scelta \"{nome}\"")
        return False
    id_opzione = campo.opzioni.get(normalizza(opzione))
    if id_opzione is None:
        avviso(f"Il campo \"{nome}\" del Project non ha l'opzione \"{opzione}\" "
               f"(ci sono: {', '.join(campo.opzioni)})")
        return False
    _imposta(gh, project, item, campo, {"singleSelectOptionId": id_opzione})
    return True


def imposta_iterazione(gh: GitHub, project: Project, item: str, nome: str, giorno: date) -> bool:
    campo = project.campo(nome)
    if campo is None or campo.tipo != "ITERATION":
        avviso(f"Nel Project manca il campo iterazione \"{nome}\"")
        return False
    it = iterazione_del_giorno(campo, giorno)
    if it is None:
        avviso(f"Nessuna iterazione del campo \"{nome}\" contiene il {giorno.isoformat()}")
        return False
    _imposta(gh, project, item, campo, {"iterationId": it["id"]})
    return True
