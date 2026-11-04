"""
metriche.py -- le metriche mostrate nel cruscotto.

Per ora ci sono alcune metriche di processo ricavabili dalle ore. Quando il
Piano di Qualifica definirà le metriche ufficiali (con codice, formula e
soglie), si aggiungono qui:

  1. scrivete una funzione che riceve l'Analisi e restituisce una Metrica;
  2. aggiungetela alla lista METRICHE in fondo al file.

Il cruscotto le mostra da sole, nell'ordine della lista.

Le soglie usate per l'esito (ok / attenzione) sono PROVVISORIE: vanno
sostituite con quelle del Piano di Qualifica.
"""

from __future__ import annotations

from dataclasses import dataclass

from calcoli import Analisi


@dataclass
class Metrica:
    codice: str               # come nel Piano di Qualifica, es. "MPC-SV"
    nome: str
    valore: str               # già formattato, es. "12 %"
    descrizione: str          # formula o significato, in breve
    esito: str = ""           # "ok", "attenzione", "" (non valutata)


def percento(x: float) -> str:
    """12.4 -> '+12 %'; -3 -> '-3 %'; 0.2 -> '0 %'."""
    v = round(x)
    return "0 %" if v == 0 else f"{v:+d} %"


def scostamento_stime(a: Analisi) -> Metrica:
    """Quanto le ore effettive delle issue chiuse si discostano dalle stimate."""
    coppie = [(x.ore_stimate, sum(v.ore for v in x.voci)) for x in a.dati.attivita
              if x.chiusa and x.ore_stimate and x.voci]
    if not coppie:
        return Metrica("M-STIME", "Scostamento delle stime", "—",
                       "(effettive − stimate) / stimate, sulle issue chiuse con stima e ore")
    stimate = sum(s for s, _ in coppie)
    effettive = sum(e for _, e in coppie)
    valore = (effettive - stimate) / stimate * 100
    return Metrica("M-STIME", "Scostamento delle stime", f"{percento(valore)} su {len(coppie)} issue",
                   "(effettive − stimate) / stimate, sulle issue chiuse con stima e ore",
                   "ok" if abs(valore) <= 20 else "attenzione")


def consumo_budget(a: Analisi) -> Metrica:
    """Budget consumato rispetto al tempo trascorso (1 = in linea)."""
    preventivo = a.costo(a.matrice_preventivo())
    consumato = a.costo(a.matrice_effettive())
    if not a.conf.sprint or not a.conf.fine_progetto or not preventivo:
        return Metrica("M-BUDGET", "Consumo del budget rispetto al tempo", "—",
                       "(costo consumato / preventivo) / (giorni trascorsi / giorni totali)")
    inizio = a.conf.sprint[0].inizio
    totali = (a.conf.fine_progetto - inizio).days or 1
    trascorsi = min(max((a.oggi - inizio).days + 1, 1), totali)
    indice = (consumato / preventivo) / (trascorsi / totali)
    return Metrica("M-BUDGET", "Consumo del budget rispetto al tempo", f"{indice:.2f}".replace(".", ","),
                   "(costo consumato / preventivo) / (giorni trascorsi / giorni totali): "
                   "sotto 1 si spende meno del previsto, sopra 1 di più",
                   "ok" if 0.8 <= indice <= 1.2 else "attenzione")


def ore_fuori_piano(a: Analisi) -> Metrica:
    totale = a.ore()
    fuori = sum(v.ore for v in a.dati.voci if v.fuori_piano)
    if not totale:
        return Metrica("M-PIANO", "Ore fuori pianificazione", "—",
                       "ore in un ruolo non pianificato / ore totali")
    valore = fuori / totale * 100
    return Metrica("M-PIANO", "Ore fuori pianificazione", f"{valore:.0f} %",
                   "ore in un ruolo non pianificato (o fuori dagli sprint) / ore totali",
                   "ok" if valore <= 10 else "attenzione")


def obiettivi_raggiunti(a: Analisi) -> Metrica:
    valutabili = [s.raggiunto for sp in a.sprint_conclusi for s in a.stato_obiettivi(sp)
                  if s.raggiunto is not None]
    if not valutabili:
        return Metrica("M-OBIETTIVI", "Obiettivi raggiunti negli sprint conclusi", "—",
                       "obiettivi con tutte le issue chiuse / obiettivi con issue collegate")
    valore = sum(valutabili) / len(valutabili) * 100
    return Metrica("M-OBIETTIVI", "Obiettivi raggiunti negli sprint conclusi",
                   f"{valore:.0f} % ({sum(valutabili)}/{len(valutabili)})",
                   "obiettivi con tutte le issue chiuse / obiettivi con issue collegate",
                   "ok" if valore >= 80 else "attenzione")


def scostamento_sprint(a: Analisi) -> Metrica:
    """Ore effettive contro pianificate, sugli sprint conclusi."""
    pianificate = sum(sum(sum(r.values()) for r in s.ruoli.values()) for s in a.sprint_conclusi)
    effettive = sum(a.ore(sprint=s.numero) for s in a.sprint_conclusi)
    if not pianificate:
        return Metrica("M-SPRINT", "Ore effettive rispetto alle pianificate", "—",
                       "(effettive − pianificate) / pianificate, sugli sprint conclusi")
    valore = (effettive - pianificate) / pianificate * 100
    return Metrica("M-SPRINT", "Ore effettive rispetto alle pianificate", percento(valore),
                   "(effettive − pianificate) / pianificate, sugli sprint conclusi",
                   "ok" if abs(valore) <= 15 else "attenzione")


METRICHE = [scostamento_sprint, consumo_budget, scostamento_stime, obiettivi_raggiunti, ore_fuori_piano]


def calcola(a: Analisi) -> list[Metrica]:
    return [f(a) for f in METRICHE]
