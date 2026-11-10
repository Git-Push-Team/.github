"""
registro_ore.py -- legge i comandi /ore scritti nei commenti.

Sintassi (una riga per comando, anche più righe nello stesso commento):

    /ore 14:00-16:30             dalle 14 alle 16:30 (2,5 ore), nel ruolo pianificato
                                 per voi nello sprint: il bot calcola la durata
    /ore 9-11 verificatore       dalle 9 alle 11, da Verificatore
    /ore 21:00-22:30 analista 2026-11-05   con la data del lavoro (se non è oggi)

Vale ancora la vecchia forma con il solo totale (i commenti già scritti
restano validi), ma l'orario è meglio perché si può controllare:

    /ore 2                       2 ore, nel ruolo pianificato per voi nello sprint
    /ore 1,5 verificatore        1 ora e mezza da Verificatore
    /ore 1h30 analista 2026-11-05   con la data del lavoro (se non è oggi)
    /ore 45m                     45 minuti

Il bot segnala, senza scartare le ore (funzione controlla):
  - due intervalli della stessa persona che si sovrappongono;
  - più di ORE_MASSIME_GIORNO ore della stessa persona nello stesso giorno;
  - ore segnate più di GIORNI_RITARDO giorni dopo il lavoro.

- le ore valgono per chi scrive il commento: nessuno può segnarle per un altro;
- per correggere si modifica o si cancella il commento: i totali si ricalcolano;
- le righe dentro un blocco di codice (```) non contano.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from comune import Configurazione, ore_testo, ruolo_da_testo

MARCATORE = "<!-- riepilogo-ore -->"      # il commento di riepilogo del bot
COMANDO = re.compile(r"^\s*/ore(?:\s+(.*))?$", re.IGNORECASE)
ORE_MASSIME = 12                           # per singolo comando
ORE_MASSIME_GIORNO = 8                     # oltre, il giorno si segnala (le ore contano lo stesso)
GIORNI_RITARDO = 3                         # ore segnate più di tanti giorni dopo: si segnalano
MARGINE = timedelta(minutes=30)            # un intervallo può finire poco dopo il commento
# 14:00-16:30, 14.00-16.30, 9-11, 23:30-00:30 (a cavallo della mezzanotte)
INTERVALLO = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?\s*[-–—]\s*(\d{1,2})(?:[:.](\d{2}))?(?=\s|$)")


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
    inizio: time | None = None       # con /ore 14:00-16:30: l'orario (None con il solo totale)
    fine: time | None = None
    scritto_il: date | None = None   # giorno del commento (per le ore segnate in ritardo)

    @property
    def orario(self) -> str:
        """'14:00–16:30', oppure '' con il solo totale."""
        return f"{self.inizio:%H:%M}–{self.fine:%H:%M}" if self.inizio and self.fine else ""

    def intervallo(self) -> tuple[datetime, datetime] | None:
        """Inizio e fine come date e ore (la fine può essere il giorno dopo)."""
        if not (self.inizio and self.fine):
            return None
        a = datetime.combine(self.giorno, self.inizio)
        return a, a + timedelta(hours=self.ore)


@dataclass
class Segnalazione:
    tipo: str               # "Intervalli sovrapposti", "Troppe ore in un giorno"...
    testo: str
    url: str = ""


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


def leggi_intervallo(m: re.Match) -> tuple[time, time, float] | str:
    """Il match di INTERVALLO -> (inizio, fine, ore), oppure il motivo dell'errore."""
    h1, m1, h2, m2 = (int(x) if x else 0 for x in m.groups())
    if h1 > 23 or h2 > 24 or m1 > 59 or m2 > 59 or (h2 == 24 and m2):
        return f"\"{m.group(0)}\" non è un orario valido (esempio: 14:00-16:30)"
    minuti = (h2 * 60 + m2 - h1 * 60 - m1) % (24 * 60)
    if minuti == 0:
        return f"in \"{m.group(0)}\" inizio e fine coincidono"
    return time(h1, m1), time(h2 % 24, m2), minuti / 60


def interpreta(riga: str, giorno_commento: date, chiave: str,
               conf: Configurazione) -> tuple[float, str, date, bool] | str:
    """Una riga /ore -> (ore, ruolo, giorno, fuori_piano), oppure il motivo dell'errore."""
    esito = interpreta_completo(riga, giorno_commento, chiave, conf)
    return esito if isinstance(esito, str) else esito[:4]


def interpreta_completo(riga: str, giorno_commento: date, chiave: str, conf: Configurazione,
                        ora_commento: time | None = None
                        ) -> tuple[float, str, date, bool, time | None, time | None] | str:
    """Come interpreta, più inizio e fine dell'intervallo (None con il solo totale).
    Con ora_commento controlla anche che l'intervallo non finisca dopo il commento."""
    resto = (COMANDO.match(riga).group(1) or "").strip()
    inizio = fine = None
    intervallo = INTERVALLO.match(resto)
    if intervallo:                                   # /ore 14:00-16:30 ...
        letto = leggi_intervallo(intervallo)
        if isinstance(letto, str):
            return letto
        inizio, fine, ore = letto
        if ore > ORE_MASSIME:
            return (f"{intervallo.group(0)} sono {ore_testo(ore)} ore: al massimo {ORE_MASSIME} "
                    "per comando (se avete scambiato inizio e fine, correggete)")
        parole = [p for p in resto[intervallo.end():].split() if p.lower() not in ("ore", "ora", "h")]
    else:                                            # /ore 2 ... (vecchia forma)
        parole = [p for p in resto.split() if p.lower() not in ("ore", "ora", "h")]
        if not parole:
            return "mancano le ore (esempio: /ore 14:00-16:30 oppure /ore 2 verificatore)"
        ore = leggi_ore(parole[0])
        if ore is None:
            return (f"\"{parole[0]}\" non è un orario né un numero di ore "
                    "(esempi: 14:00-16:30, 2, 1,5, 1h30, 45m)")
        if ore <= 0 or ore > ORE_MASSIME:
            return f"{parole[0]} ore: il valore deve essere tra 0 e {ORE_MASSIME}"
        parole = parole[1:]
    ruolo, giorno, con_data = None, giorno_commento, False
    for parola in parole:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", parola):
            try:
                giorno = date.fromisoformat(parola)
            except ValueError:
                return f"la data \"{parola}\" non esiste"
            if giorno > giorno_commento:
                return f"la data {parola} è nel futuro"
            con_data = True
        elif ruolo_da_testo(parola):
            ruolo = ruolo_da_testo(parola)
        else:
            return (f"non capisco \"{parola}\": dopo le ore si scrive il ruolo e, se serve, "
                    "la data AAAA-MM-GG")
    if inizio is not None and ora_commento is not None:
        # a cavallo della mezzanotte e senza data: è cominciato il giorno prima
        if not con_data and fine <= inizio and ora_commento < inizio:
            giorno = giorno_commento - timedelta(days=1)
        termine = datetime.combine(giorno, inizio) + timedelta(hours=ore)
        if termine > datetime.combine(giorno_commento, ora_commento) + MARGINE:
            return (f"l'intervallo {intervallo.group(0)} finisce dopo l'ora del commento "
                    f"({ora_commento:%H:%M} del {giorno_commento.isoformat()}): se il lavoro è di "
                    "un altro giorno aggiungete la data (es. /ore 14:00-16:30 2026-11-05); "
                    "se è lavoro fatto dopo, scrivetelo in un commento nuovo")
    sprint = conf.sprint_di(giorno)
    if ruolo is None:
        ruolo = sprint.ruolo_principale(chiave) if sprint else None
        if ruolo is None:
            return (f"non avete un ruolo pianificato il {giorno.isoformat()}: scrivete il ruolo, "
                    "per esempio /ore 2 analista")
    fuori_piano = sprint is None or ruolo not in sprint.ruoli.get(chiave, {})
    return round(ore, 2), ruolo, giorno, fuori_piano, inizio, fine


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
        istante = datetime.fromisoformat(c["createdAt"].replace("Z", "+00:00")).astimezone(conf.fuso)
        giorno = istante.date()
        for riga in righe:
            esito = interpreta_completo(riga, giorno, membro.chiave, conf, istante.time())
            if isinstance(esito, str):
                scarti.append(Scarto(login, riga, esito, fonte, c.get("url", "")))
                continue
            ore, ruolo, quando, fuori_piano, inizio, fine = esito
            sprint = conf.sprint_di(quando)
            voci.append(Voce(membro.chiave, ruolo, ore, quando, sprint.numero if sprint else None,
                             fuori_piano, fonte, c.get("id", ""), c.get("url", ""),
                             inizio, fine, giorno))
    return voci, scarti


def controlla(voci: list[Voce], conf: Configurazione) -> list[Segnalazione]:
    """Cose da controllare nelle ore registrate (le ore contano lo stesso):
    intervalli sovrapposti, troppe ore in un giorno, ore segnate in ritardo."""
    def nome(chiave: str) -> str:
        return conf.membri[chiave].nome if chiave in conf.membri else chiave

    segnalazioni = []
    # 1. intervalli della stessa persona che si sovrappongono (anche tra issue diverse)
    per_persona = defaultdict(list)
    for v in voci:
        if v.intervallo():
            per_persona[v.persona].append(v)
    for persona, elenco in per_persona.items():
        elenco.sort(key=lambda v: v.intervallo())
        for i, v1 in enumerate(elenco):
            fine1 = v1.intervallo()[1]
            for v2 in elenco[i + 1:]:
                if v2.intervallo()[0] >= fine1:
                    break
                segnalazioni.append(Segnalazione(
                    "Intervalli sovrapposti",
                    f"{nome(persona)}, {v1.giorno.isoformat()}: {v1.orario} ({v1.fonte}) e "
                    f"{v2.orario}" + (f" del {v2.giorno.isoformat()}" if v2.giorno != v1.giorno else "")
                    + f" ({v2.fonte}): le stesse ore contate due volte?", v2.url))
    # 2. più di ORE_MASSIME_GIORNO ore in un giorno
    per_giorno = defaultdict(list)
    for v in voci:
        per_giorno[(v.persona, v.giorno)].append(v)
    for (persona, giorno), elenco in sorted(per_giorno.items(), key=lambda x: (x[0][1], x[0][0])):
        totale = sum(v.ore for v in elenco)
        if totale > ORE_MASSIME_GIORNO + 1e-9:
            dove = ", ".join(sorted({v.fonte for v in elenco}))
            segnalazioni.append(Segnalazione(
                "Troppe ore in un giorno",
                f"{nome(persona)}, {giorno.isoformat()}: {ore_testo(totale)} ore, più di "
                f"{ORE_MASSIME_GIORNO} ({dove})", elenco[-1].url))
    # 3. ore segnate più di GIORNI_RITARDO giorni dopo il lavoro
    for v in sorted(voci, key=lambda v: (v.giorno, v.persona)):
        if v.scritto_il and (v.scritto_il - v.giorno).days > GIORNI_RITARDO:
            segnalazioni.append(Segnalazione(
                "Ore segnate in ritardo",
                f"{nome(v.persona)}, {ore_testo(v.ore)} h del {v.giorno.isoformat()} segnate il "
                f"{v.scritto_il.isoformat()}, {(v.scritto_il - v.giorno).days} giorni dopo "
                f"({v.fonte})", v.url))
    return segnalazioni
