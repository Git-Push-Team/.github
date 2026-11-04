"""
comune.py -- pezzi condivisi: configurazione, ruoli, sprint, accesso a GitHub.

Non si lancia da solo: lo usano ore.py, progetto.py e cruscotto.py.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CARTELLA = Path(__file__).resolve().parent
CONFIGURAZIONE = CARTELLA / "pianificazione.toml"

# Nome ufficiale di ogni ruolo e i modi abbreviati accettati da /ore
RUOLI = ["Responsabile", "Amministratore", "Analista", "Progettista",
         "Programmatore", "Verificatore"]
SIGLE = {"Responsabile": "Re", "Amministratore": "Am", "Analista": "An",
         "Progettista": "Pt", "Programmatore": "Pr", "Verificatore": "Ve"}
ALIAS = {
    "responsabile": "Responsabile", "resp": "Responsabile", "re": "Responsabile",
    "amministratore": "Amministratore", "amm": "Amministratore", "am": "Amministratore",
    "admin": "Amministratore",
    "analista": "Analista", "an": "Analista", "analisi": "Analista",
    "progettista": "Progettista", "prog": "Progettista", "pt": "Progettista",
    "progettazione": "Progettista",
    "programmatore": "Programmatore", "progr": "Programmatore", "pr": "Programmatore",
    "dev": "Programmatore", "sviluppatore": "Programmatore",
    "verificatore": "Verificatore", "ver": "Verificatore", "ve": "Verificatore",
    "verifica": "Verificatore",
}


def ruolo_da_testo(testo: str) -> str | None:
    """'verificatore', 'Ver', 'VERIFICA' -> 'Verificatore'; altrimenti None."""
    return ALIAS.get(testo.strip().lower().rstrip(".,;:"))


# --------------------------------------------------------------------------
#  Configurazione (pianificazione.toml)
# --------------------------------------------------------------------------
@dataclass
class Membro:
    chiave: str
    nome: str
    github: str


@dataclass
class Obiettivo:
    testo: str
    issue: list[str] = field(default_factory=list)    # "docs#12", "poc#3"


@dataclass
class Sprint:
    numero: int
    inizio: date
    fine: date
    obiettivi: list[Obiettivo]
    ruoli: dict[str, dict[str, float]]                  # chiave -> {Ruolo: ore}

    @property
    def nome(self) -> str:
        return f"Sprint {self.numero}"

    def contiene(self, giorno: date) -> bool:
        return self.inizio <= giorno <= self.fine

    def ore_pianificate(self, chiave: str, ruolo: str | None = None) -> float:
        ruoli = self.ruoli.get(chiave, {})
        return sum(ruoli.values()) if ruolo is None else ruoli.get(ruolo, 0.0)

    def ruolo_principale(self, chiave: str) -> str | None:
        ruoli = self.ruoli.get(chiave, {})
        return max(ruoli, key=ruoli.get) if ruoli else None


@dataclass
class Configurazione:
    organizzazione: str
    numero_project: int
    fuso: ZoneInfo
    repo_privato: str
    campi: dict
    membri: dict[str, Membro]                           # chiave -> Membro
    tariffe: dict[str, float]                           # Ruolo -> euro/ora
    preventivo: dict[str, dict[str, float]]             # chiave -> {Ruolo: ore}
    fine_progetto: date | None
    scadenze: dict[str, date]
    sprint: list[Sprint]

    def membro_da_github(self, login: str | None) -> Membro | None:
        if not login:
            return None
        return next((m for m in self.membri.values()
                     if m.github.lower() == login.lower()), None)

    def sprint_di(self, giorno: date) -> Sprint | None:
        return next((s for s in self.sprint if s.contiene(giorno)), None)

    def oggi(self) -> date:
        return datetime.now(self.fuso).date()

    def campo(self, nome: str) -> str:
        return str(self.campi.get(nome, ""))


class ErroreConfigurazione(Exception):
    pass


def _data(valore, dove: str) -> date:
    if isinstance(valore, date) and not isinstance(valore, datetime):
        return valore
    try:
        return date.fromisoformat(str(valore))
    except ValueError:
        raise ErroreConfigurazione(f"{dove}: la data \"{valore}\" non va bene, scrivetela AAAA-MM-GG")


def _ore_per_ruolo(tabella: dict, dove: str) -> dict[str, float]:
    risultato = {}
    for nome, ore in (tabella or {}).items():
        ruolo = ruolo_da_testo(nome)
        if ruolo is None:
            raise ErroreConfigurazione(f"{dove}: ruolo \"{nome}\" sconosciuto. Ruoli validi: "
                                       + ", ".join(RUOLI))
        if not isinstance(ore, (int, float)) or ore < 0:
            raise ErroreConfigurazione(f"{dove}: le ore di {nome} devono essere un numero")
        risultato[ruolo] = risultato.get(ruolo, 0.0) + float(ore)
    return risultato


def carica_configurazione(percorso: Path | None = None) -> Configurazione:
    """Legge pianificazione.toml (o il file indicato da GESTIONE_CONFIGURAZIONE,
    usato dalle prove automatiche)."""
    percorso = Path(percorso or os.environ.get("GESTIONE_CONFIGURAZIONE") or CONFIGURAZIONE)
    try:
        dati = tomllib.loads(percorso.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as errore:
        raise ErroreConfigurazione(f"{percorso.name}: errore di scrittura ({errore})")

    org = dati.get("organizzazione", {})
    membri = {}
    for chiave, valori in dati.get("membri", {}).items():
        if not isinstance(valori, dict) or not valori.get("github"):
            raise ErroreConfigurazione(f"[membri] {chiave}: serve github = \"username\"")
        membri[chiave] = Membro(chiave, str(valori.get("nome", chiave)), str(valori["github"]))

    tariffe = {}
    for nome, euro in dati.get("ruoli", {}).items():
        ruolo = ruolo_da_testo(nome)
        if ruolo is None:
            raise ErroreConfigurazione(f"[ruoli]: ruolo \"{nome}\" sconosciuto")
        tariffe[ruolo] = float(euro)

    prev = dict(dati.get("preventivo", {}))
    fine = _data(prev.pop("fine_progetto"), "[preventivo] fine_progetto") if "fine_progetto" in prev else None
    comune = _ore_per_ruolo(prev.pop("tutti", {}), "[preventivo] tutti")
    preventivo = {}
    for chiave in membri:
        preventivo[chiave] = _ore_per_ruolo(prev[chiave], f"[preventivo] {chiave}") if chiave in prev else dict(comune)
    for chiave in prev:
        if chiave not in membri:
            raise ErroreConfigurazione(f"[preventivo]: \"{chiave}\" non è tra i [membri]")

    sprint = []
    for i, s in enumerate(dati.get("sprint", []), start=1):
        dove = f"[[sprint]] n. {s.get('numero', i)}"
        for obbligatorio in ("numero", "inizio", "fine"):
            if obbligatorio not in s:
                raise ErroreConfigurazione(f"{dove}: manca {obbligatorio}")
        ruoli = {}
        for chiave, tabella in (s.get("ruoli") or {}).items():
            if chiave not in membri:
                raise ErroreConfigurazione(f"{dove}: \"{chiave}\" non è tra i [membri]")
            ruoli[chiave] = _ore_per_ruolo(tabella, f"{dove}, {chiave}")
        obiettivi = []
        for o in s.get("obiettivi", []) or []:
            if isinstance(o, str):
                obiettivi.append(Obiettivo(o))
            else:
                obiettivi.append(Obiettivo(str(o.get("testo", "")), [str(x) for x in o.get("issue", [])]))
        nuovo = Sprint(int(s["numero"]), _data(s["inizio"], dove), _data(s["fine"], dove), obiettivi, ruoli)
        if nuovo.fine < nuovo.inizio:
            raise ErroreConfigurazione(f"{dove}: la fine è prima dell'inizio")
        if sprint and nuovo.inizio <= sprint[-1].fine:
            raise ErroreConfigurazione(f"{dove}: si sovrappone allo sprint precedente")
        sprint.append(nuovo)

    return Configurazione(
        organizzazione=str(org.get("nome", "Git-Push-Team")),
        numero_project=int(org.get("project", 1)),
        fuso=ZoneInfo(str(org.get("fuso_orario", "Europe/Rome"))),
        repo_privato=str(org.get("repo_privato", ".github-private")),
        campi=dict(dati.get("campi", {})),
        membri=membri, tariffe=tariffe, preventivo=preventivo, fine_progetto=fine,
        scadenze={k: _data(v, f"[scadenze] {k}") for k, v in dati.get("scadenze", {}).items()},
        sprint=sprint,
    )


# --------------------------------------------------------------------------
#  Accesso a GitHub (API GraphQL)
# --------------------------------------------------------------------------
class ErroreGitHub(Exception):
    pass


class GitHub:
    """Client minimo per l'API GraphQL. Il token arriva dalla variabile
    d'ambiente GH_TOKEN (nelle Actions: il token della GitHub App)."""

    URL = "https://api.github.com/graphql"

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise ErroreGitHub("Manca il token: impostate GH_TOKEN")

    def query(self, testo: str, **variabili) -> dict:
        corpo = json.dumps({"query": testo, "variables": variabili}).encode()
        for tentativo in range(4):
            richiesta = urllib.request.Request(self.URL, data=corpo, headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "git-push-team-gestione",
            })
            try:
                with urllib.request.urlopen(richiesta, timeout=60) as risposta:
                    dati = json.loads(risposta.read())
            except urllib.error.HTTPError as errore:
                if errore.code in (502, 503, 504) and tentativo < 3:
                    time.sleep(2 + 3 * tentativo)
                    continue
                raise ErroreGitHub(f"HTTP {errore.code}: {errore.read()[:300]!r}")
            except urllib.error.URLError as errore:
                if tentativo < 3:
                    time.sleep(2 + 3 * tentativo)
                    continue
                raise ErroreGitHub(str(errore))
            if dati.get("errors"):
                messaggi = "; ".join(e.get("message", "?") for e in dati["errors"])
                raise ErroreGitHub(messaggi)
            return dati["data"]
        raise ErroreGitHub("GitHub non risponde")


# Frammento GraphQL comune: i commenti di una issue o PR
COMMENTI = """
  comments(first: 100, after: $dopo_commenti) {
    pageInfo { hasNextPage endCursor }
    nodes { id url body createdAt author { login __typename } }
  }
"""


def tutti_i_commenti(gh: GitHub, nodo: dict) -> list[dict]:
    """I commenti di una issue/PR già letta, andando a prendere le pagine
    successive alla prima (oltre 100 commenti) se servono."""
    blocco = nodo.get("comments") or {}
    commenti = list(blocco.get("nodes") or [])
    info = blocco.get("pageInfo") or {}
    while info.get("hasNextPage"):
        dati = gh.query("""
            query($id: ID!, $dopo_commenti: String) {
              node(id: $id) {
                ... on Issue { %s }
                ... on PullRequest { %s }
              }
            }""" % (COMMENTI, COMMENTI), id=nodo["id"], dopo_commenti=info["endCursor"])
        blocco = dati["node"]["comments"]
        commenti += blocco["nodes"]
        info = blocco["pageInfo"]
    return commenti


# --------------------------------------------------------------------------
#  Piccole utilità
# --------------------------------------------------------------------------
def riferimento(repo_completo: str, numero: int, organizzazione: str) -> str:
    """'Git-Push-Team/docs', 12 -> 'docs#12' (repo di altre org: completo)."""
    proprietario, _, nome = repo_completo.partition("/")
    return f"{nome}#{numero}" if proprietario.lower() == organizzazione.lower() else f"{repo_completo}#{numero}"


def ore_testo(ore: float) -> str:
    """2.0 -> '2'; 1.5 -> '1,5'."""
    testo = f"{ore:.2f}".rstrip("0").rstrip(".")
    return testo.replace(".", ",")


def euro_testo(euro: float) -> str:
    """1620 -> '1.620,00 €'."""
    intero, decimali = f"{euro:,.2f}".split(".")
    return f"{intero.replace(',', '.')},{decimali} €"


def data_breve(giorno: date) -> str:
    mesi = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
    return f"{giorno.day} {mesi[giorno.month - 1]}"


def data_lunga(giorno: date) -> str:
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
            "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    return f"{giorno.day} {mesi[giorno.month - 1]} {giorno.year}"


def avviso(testo: str) -> None:
    """Un avviso visibile nel riepilogo delle GitHub Actions."""
    print(f"::warning::{testo}" if os.environ.get("GITHUB_ACTIONS") else f"AVVISO: {testo}",
          file=sys.stderr)


def normalizza(testo: str) -> str:
    """Per confrontare nomi di colonne e opzioni: 'In Review' == 'in review'."""
    return re.sub(r"\s+", " ", testo.strip().lower())
