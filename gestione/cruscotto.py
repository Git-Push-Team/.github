"""
cruscotto.py -- genera il cruscotto del gruppo. Lo lancia ogni notte il
workflow "Cruscotto"; si può provare anche sul proprio computer.

Scrive nella cartella di uscita (di solito il repository .github-private):

    README.md                 il cruscotto (pagina del repository)
    profile/README.md         lo stesso, sulla pagina dell'organizzazione (solo membri)
    tabelle/*.tex             tabelle per il Piano di Progetto
    diario/sprint-N.md        i numeri di ogni sprint per il diario di bordo
    dati/ore.csv              tutte le ore registrate (per Excel / Google Fogli)

Uso:
    python3 gestione/cruscotto.py --uscita cartella                 (legge da GitHub, serve GH_TOKEN)
    python3 gestione/cruscotto.py --uscita cartella --da-file dati.json   (prova, senza GitHub)
    python3 gestione/cruscotto.py --uscita cartella --salva-dati dati.json
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

from calcoli import Analisi
from comune import ErroreConfigurazione, ErroreGitHub, avviso, carica_configurazione
from dati import leggi
from uscite import cruscotto, diario, leggimi_tabelle, registro_csv, tabelle_latex


def scrivi(percorso: Path, testo: str) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    percorso.write_text(testo, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera il cruscotto del gruppo")
    parser.add_argument("--uscita", required=True, type=Path, help="cartella in cui scrivere i file")
    parser.add_argument("--da-file", type=Path, help="legge i dati da un JSON invece che da GitHub")
    parser.add_argument("--salva-dati", type=Path, help="salva i dati letti da GitHub in un JSON")
    parser.add_argument("--oggi", help="data di riferimento AAAA-MM-GG (per le prove)")
    argomenti = parser.parse_args(argv)

    try:
        conf = carica_configurazione()
    except ErroreConfigurazione as errore:
        avviso(f"pianificazione.toml: {errore}")
        return 1
    oggi = date.fromisoformat(argomenti.oggi or os.environ.get("CRUSCOTTO_OGGI", "") or conf.oggi().isoformat())
    try:
        dati = leggi(conf, da_file=argomenti.da_file, salva_in=argomenti.salva_dati)
    except ErroreGitHub as errore:
        avviso(f"Errore con GitHub: {errore}")
        return 1

    analisi = Analisi(conf, dati, oggi)
    adesso = datetime.now(conf.fuso)
    if argomenti.oggi or os.environ.get("CRUSCOTTO_OGGI"):
        adesso = adesso.replace(year=oggi.year, month=oggi.month, day=oggi.day)

    uscita = argomenti.uscita
    testo = cruscotto(analisi, adesso)
    scrivi(uscita / "README.md", testo)
    scrivi(uscita / "profile" / "README.md", testo)
    tabelle = tabelle_latex(analisi)
    for nome, contenuto in tabelle.items():
        scrivi(uscita / "tabelle" / nome, contenuto)
    scrivi(uscita / "tabelle" / "README.md", leggimi_tabelle(list(tabelle)))
    for s in analisi.sprint_iniziati:
        scrivi(uscita / "diario" / f"sprint-{s.numero}.md", diario(analisi, s))
    scrivi(uscita / "dati" / "ore.csv", registro_csv(analisi))

    print(f"Cruscotto: {len(dati.attivita)} attività, {len(dati.voci)} registrazioni di ore, "
          f"{len(analisi.anomalie)} cose da sistemare, {len(tabelle)} tabelle LaTeX")
    for a in analisi.anomalie:
        if a.tipo == "Comando /ore non valido":
            avviso(a.testo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
