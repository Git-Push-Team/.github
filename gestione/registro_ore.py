"""
registro_ore.py -- legge i comandi /ore scritti nei commenti.

Sintassi (una riga per comando, anche più righe nello stesso commento):

    /ore 2                       2 ore, nel ruolo pianificato per voi nello sprint
    /ore 1,5 verificatore        1 ora e mezza da Verificatore
    /ore 1h30 analista 2026-11-05   con la data del lavoro (se non è oggi)
    /ore 45m                     45 minuti

- le ore valgono per chi scrive il commento: nessuno può segnarle per un altro;
- per correggere si modifica o si cancella il commento: i totali si ricalcolano;
- le righe dentro un blocco di codice (```) non contano.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from comune import Configurazione, ruolo_da_testo

MARCATORE = "<!-- riepilogo-ore -->"      # il commento di riepilogo del bot
COMANDO = re.compile(r"^\s*/ore(?:\s+(.*))?$", re.IGNORECASE)
ORE_MASSIME = 12                           # per singolo comando


@dataclass
class Voce:
    persona: str            # chiave del membro
    ruolo: str
    ore: float
    giorno: date
    sprint: int | None      # numero dello sprint che contiene il giorno
    fuori_piano: bool       # ruolo non pianificato per quella persona in quello sprint
    fonte: str              # dove è scritto il comando, es. "docs#12"
    commento: str           # id del commento
    url: str


@dataclass
class Scarto:
    autore: str             # username GitHub
    riga: str
    motivo: str
    fonte: str
    url: str


def leggi_ore(testo: str) -> float | None:
    """'2' '1.5' '1,5' '2h' '1h30' '1h30m' '45m' '90min' -> ore; altrimenti None."""
    t = testo.strip().lower()
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*h?", t)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.fullmatch(r"(\d+)h(\d{1,2})m?", t)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60
    m = re.fullmatch(r"(\d+)\s*m(?:in)?", t)
    if m:
        return int(m.group(1)) / 60
    return None


def righe_di_comando(corpo: str) -> list[str]:
    """Le righe /ore di un commento, saltando i blocchi di codice."""
    righe, in_codice = [], False
    for riga in corpo.splitlines():
        if riga.strip().startswith("```"):
            in_codice = not in_codice
            continue
        if not in_codice and COMANDO.match(riga):
            righe.append(riga.strip())
    return righe


def giorno_locale(istante: str, conf: Configurazione) -> date:
    """'2026-11-03T20:15:00Z' -> la data nel fuso del gruppo."""
    return datetime.fromisoformat(istante.replace("Z", "+00:00")).astimezone(conf.fuso).date()


def interpreta(riga: str, giorno_commento: date, chiave: str,
               conf: Configurazione) -> tuple[float, str, date, bool] | str:
    """Una riga /ore -> (ore, ruolo, giorno, fuori_piano), oppure il motivo dell'errore."""
    resto = COMANDO.match(riga).group(1) or ""
    parole = [p for p in resto.split() if p.lower() not in ("ore", "ora", "h")]
    if not parole:
        return "manca il numero di ore (esempio: /ore 2 verificatore)"
    ore = leggi_ore(parole[0])
    if ore is None:
        return f"\"{parole[0]}\" non è un numero di ore (esempi: 2, 1,5, 1h30, 45m)"
    if ore <= 0 or ore > ORE_MASSIME:
        return f"{parole[0]} ore: il valore deve essere tra 0 e {ORE_MASSIME}"
    ruolo, giorno = None, giorno_commento
    for parola in parole[1:]:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", parola):
            try:
                giorno = date.fromisoformat(parola)
            except ValueError:
                return f"la data \"{parola}\" non esiste"
            if giorno > giorno_commento:
                return f"la data {parola} è nel futuro"
        elif ruolo_da_testo(parola):
            ruolo = ruolo_da_testo(parola)
        else:
            return (f"non capisco \"{parola}\": dopo le ore si scrive il ruolo e, se serve, "
                    "la data AAAA-MM-GG")
    sprint = conf.sprint_di(giorno)
    if ruolo is None:
        ruolo = sprint.ruolo_principale(chiave) if sprint else None
        if ruolo is None:
            return (f"non avete un ruolo pianificato il {giorno.isoformat()}: scrivete il ruolo, "
                    "per esempio /ore 2 analista")
    fuori_piano = sprint is None or ruolo not in sprint.ruoli.get(chiave, {})
    return round(ore, 2), ruolo, giorno, fuori_piano


def voci_da_commenti(commenti: list[dict], fonte: str,
                     conf: Configurazione) -> tuple[list[Voce], list[Scarto]]:
    """Tutti i comandi /ore di una lista di commenti (formato dell'API GraphQL)."""
    voci, scarti = [], []
    for c in commenti:
        autore = c.get("author") or {}
        corpo = c.get("body") or ""
        if autore.get("__typename") == "Bot" or MARCATORE in corpo:
            continue
        righe = righe_di_comando(corpo)
        if not righe:
            continue
        login = autore.get("login") or "?"
        membro = conf.membro_da_github(login)
        if membro is None:
            scarti += [Scarto(login, r, "chi ha scritto il commento non è tra i membri del gruppo",
                              fonte, c.get("url", "")) for r in righe]
            continue
        giorno = giorno_locale(c["createdAt"], conf)
        for riga in righe:
            esito = interpreta(riga, giorno, membro.chiave, conf)
            if isinstance(esito, str):
                scarti.append(Scarto(login, riga, esito, fonte, c.get("url", "")))
                continue
            ore, ruolo, quando, fuori_piano = esito
            sprint = conf.sprint_di(quando)
            voci.append(Voce(membro.chiave, ruolo, ore, quando, sprint.numero if sprint else None,
                             fuori_piano, fonte, c.get("id", ""), c.get("url", "")))
    return voci, scarti
