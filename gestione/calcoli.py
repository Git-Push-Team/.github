"""
calcoli.py -- i conti del cruscotto: ore e costi per persona, ruolo e
sprint, confronto con il preventivo, stato degli obiettivi, anomalie.

Tutto parte da due fonti: pianificazione.toml (cosa avevamo previsto) e
i comandi /ore letti dal Project (cosa abbiamo fatto davvero).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from comune import RUOLI, Configurazione, Obiettivo, Sprint, ore_testo
from dati import Attivita, DatiProject
from registro_ore import Voce


@dataclass
class StatoObiettivo:
    obiettivo: Obiettivo
    chiuse: list[str]
    aperte: list[str]
    sconosciute: list[str]          # riferimenti non trovati nel Project

    @property
    def raggiunto(self) -> bool | None:
        """True/False se l'obiettivo ha issue collegate; None se va valutato a mano."""
        if not self.obiettivo.issue:
            return None
        return not self.aperte and not self.sconosciute


@dataclass
class Anomalia:
    tipo: str
    testo: str
    url: str = ""


@dataclass
class Analisi:
    conf: Configurazione
    dati: DatiProject
    oggi: date
    anomalie: list[Anomalia] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.persone = list(self.conf.membri)
        self.attivita_per_rif = {a.rif: a for a in self.dati.attivita}
        self._trova_anomalie()

    # ---- somme di base ---------------------------------------------------
    def voci(self, sprint: int | None = None, persona: str | None = None,
             ruolo: str | None = None, fino_a: date | None = None) -> list[Voce]:
        return [v for v in self.dati.voci
                if (sprint is None or v.sprint == sprint)
                and (persona is None or v.persona == persona)
                and (ruolo is None or v.ruolo == ruolo)
                and (fino_a is None or v.giorno <= fino_a)]

    def ore(self, **filtri) -> float:
        return sum(v.ore for v in self.voci(**filtri))

    def matrice_effettive(self, sprint: int | None = None) -> dict[str, dict[str, float]]:
        m = {p: {r: 0.0 for r in RUOLI} for p in self.persone}
        for v in self.voci(sprint=sprint):
            m[v.persona][v.ruolo] += v.ore
        return m

    def matrice_pianificate(self, sprint: Sprint) -> dict[str, dict[str, float]]:
        return {p: {r: sprint.ruoli.get(p, {}).get(r, 0.0) for r in RUOLI} for p in self.persone}

    def matrice_preventivo(self) -> dict[str, dict[str, float]]:
        return {p: {r: self.conf.preventivo.get(p, {}).get(r, 0.0) for r in RUOLI} for p in self.persone}

    def costo(self, matrice: dict[str, dict[str, float]]) -> float:
        return sum(ore * self.conf.tariffe.get(r, 0) for riga in matrice.values() for r, ore in riga.items())

    @staticmethod
    def per_ruolo(matrice: dict[str, dict[str, float]]) -> dict[str, float]:
        totali = defaultdict(float)
        for riga in matrice.values():
            for r, ore in riga.items():
                totali[r] += ore
        return {r: totali[r] for r in RUOLI}

    # ---- sprint ----------------------------------------------------------
    @property
    def sprint_corrente(self) -> Sprint | None:
        return self.conf.sprint_di(self.oggi)

    @property
    def sprint_conclusi(self) -> list[Sprint]:
        return [s for s in self.conf.sprint if s.fine < self.oggi]

    @property
    def sprint_iniziati(self) -> list[Sprint]:
        return [s for s in self.conf.sprint if s.inizio <= self.oggi]

    @property
    def ultimo_concluso(self) -> Sprint | None:
        return self.sprint_conclusi[-1] if self.sprint_conclusi else None

    @property
    def prossimo(self) -> Sprint | None:
        return next((s for s in self.conf.sprint if s.inizio > self.oggi), None)

    def stato_obiettivi(self, sprint: Sprint) -> list[StatoObiettivo]:
        risultato = []
        for o in sprint.obiettivi:
            chiuse, aperte, sconosciute = [], [], []
            for rif in o.issue:
                a = self.attivita_per_rif.get(rif)
                (sconosciute if a is None else chiuse if a.chiusa else aperte).append(rif)
            risultato.append(StatoObiettivo(o, chiuse, aperte, sconosciute))
        return risultato

    def attivita_dello_sprint(self, sprint: Sprint) -> list[Attivita]:
        """Le attività con il campo Sprint su questo sprint (o, se il campo è
        vuoto, con ore registrate nel periodo dello sprint)."""
        scelte = []
        for a in self.dati.attivita:
            if a.sprint_inizio is not None:
                if sprint.contiene(a.sprint_inizio):
                    scelte.append(a)
            elif any(v.sprint == sprint.numero for v in a.voci):
                scelte.append(a)
        return scelte

    # ---- anomalie --------------------------------------------------------
    def _trova_anomalie(self) -> None:
        for s in self.dati.scarti:
            self.anomalie.append(Anomalia("Comando /ore non valido",
                                          f"{s.fonte}, {s.autore}: `{s.riga}` → {s.motivo}", s.url))
        for v in self.dati.voci:
            if v.sprint is None:
                self.anomalie.append(Anomalia("Ore fuori dagli sprint",
                                              f"{self.conf.membri[v.persona].nome}, {ore_testo(v.ore)} h "
                                              f"il {v.giorno.isoformat()} ({v.fonte}): nessuno sprint "
                                              "pianificato in quella data", v.url))
            elif v.fuori_piano:
                self.anomalie.append(Anomalia("Ruolo non pianificato",
                                              f"{self.conf.membri[v.persona].nome}, {ore_testo(v.ore)} h da "
                                              f"{v.ruolo} nello sprint {v.sprint} ({v.fonte})", v.url))
        for a in self.dati.attivita:
            if a.tipo == "Issue" and a.chiusa and not a.voci:
                self.anomalie.append(Anomalia("Issue chiusa senza ore",
                                              f"{a.rif} «{a.titolo}»", a.url))
        corrente = self.sprint_corrente
        if corrente:
            senza = [self.conf.membri[p].nome for p in self.persone if not corrente.ruoli.get(p)]
            if senza:
                self.anomalie.append(Anomalia("Pianificazione incompleta",
                                              f"{corrente.nome}: manca il ruolo di " + ", ".join(senza)))
        elif self.conf.sprint and self.oggi <= self.conf.sprint[-1].fine:
            self.anomalie.append(Anomalia("Pianificazione incompleta", "oggi non c'è nessuno sprint"))
        elif not self.conf.sprint or self.oggi > self.conf.sprint[-1].fine:
            self.anomalie.append(Anomalia("Pianificazione incompleta",
                                          "non c'è nessuno sprint pianificato da oggi in poi: "
                                          "aggiungetene uno in pianificazione.toml"))
