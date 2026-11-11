"""
Prove automatiche degli script di gestione. Si lanciano con

    python3 -m unittest discover -s gestione/test -v

(dalla cartella principale del repository .github). Usano solo dati
inventati: non si collegano a GitHub.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import date, time
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parent))
os.environ["GESTIONE_CONFIGURAZIONE"] = str(QUI / "esempio-pianificazione.toml")

import cruscotto                                      # noqa: E402
import ore                                            # noqa: E402
import progetto                                       # noqa: E402
from calcoli import Analisi                           # noqa: E402
from comune import ErroreConfigurazione, carica_configurazione  # noqa: E402
from dati import leggi                                # noqa: E402
from dati import DatiProject                          # noqa: E402
from registro_ore import (controlla, interpreta, interpreta_completo, leggi_ore,  # noqa: E402
                          voci_da_commenti)
from uscite import registro_csv                       # noqa: E402

CONF = carica_configurazione()


def commento(login, corpo, quando="2026-11-05T19:00:00Z", bot=False, id_="C1"):
    return {"id": id_, "url": "u", "body": corpo, "createdAt": quando,
            "author": {"login": login, "__typename": "Bot" if bot else "User"}}


class ComandoOre(unittest.TestCase):
    def test_formati_delle_ore(self):
        for testo, atteso in [("2", 2), ("1.5", 1.5), ("1,5", 1.5), ("2h", 2), ("1h30", 1.5),
                              ("1h30m", 1.5), ("45m", 0.75), ("90min", 1.5)]:
            self.assertAlmostEqual(leggi_ore(testo), atteso, msg=testo)
        for testo in ["abc", "1:30", "-2", ""]:
            self.assertIsNone(leggi_ore(testo), msg=testo)

    def test_ruolo_predefinito_dallo_sprint(self):
        # spagnoli nello sprint 1: Responsabile 8, Verificatore 2 -> Responsabile
        ore_, ruolo, giorno, fuori = interpreta("/ore 2", date(2026, 11, 5), "spagnoli", CONF)
        self.assertEqual((ore_, ruolo, fuori), (2, "Responsabile", False))
        _, ruolo, _, fuori = interpreta("/ore 1 ver", date(2026, 11, 5), "spagnoli", CONF)
        self.assertEqual((ruolo, fuori), ("Verificatore", False))

    def test_ruolo_non_pianificato_e_data(self):
        _, ruolo, giorno, fuori = interpreta("/ore 1 programmatore 2026-11-03", date(2026, 11, 5),
                                             "mazzurana", CONF)
        self.assertEqual((ruolo, giorno, fuori), ("Programmatore", date(2026, 11, 3), True))

    def test_errori(self):
        self.assertIn("futuro", interpreta("/ore 1 2026-11-30", date(2026, 11, 5), "corro", CONF))
        self.assertIn("non capisco", interpreta("/ore 1 boh", date(2026, 11, 5), "corro", CONF))
        self.assertIn("tra 0 e", interpreta("/ore 20", date(2026, 11, 5), "corro", CONF))
        self.assertIn("manca", interpreta("/ore", date(2026, 11, 5), "corro", CONF))
        # fuori dagli sprint senza ruolo: va scritto il ruolo
        self.assertIn("scrivete il ruolo", interpreta("/ore 1", date(2026, 12, 20), "corro", CONF))

    def test_commenti(self):
        commenti = [
            commento("firestone109", "testo\n/ore 2\n/ORE 1,5 analista\n```\n/ore 9\n```", id_="A"),
            commento("bot", "<!-- riepilogo-ore -->\n/ore 3", bot=True, id_="B"),
            commento("estraneo", "/ore 4", id_="C"),
            commento("MaZzU05", "/ore pippo", id_="D"),
        ]
        voci, scarti = voci_da_commenti(commenti, "docs#1", CONF)
        self.assertEqual([(v.persona, v.ruolo, v.ore) for v in voci],
                         [("guglielmo", "Amministratore", 2), ("guglielmo", "Analista", 1.5)])
        self.assertTrue(voci[1].fuori_piano)
        self.assertEqual(len(scarti), 2)


class OreConOrario(unittest.TestCase):
    """/ore 14:00-16:30: il bot calcola la durata; la vecchia forma vale ancora."""
    GIORNO = date(2026, 11, 5)

    def esito(self, riga, ora=time(23, 59), giorno=None):
        return interpreta_completo(riga, giorno or self.GIORNO, "spagnoli", CONF, ora)

    def test_intervalli(self):
        for riga, atteso in [("/ore 14:00-16:30", (2.5, time(14), time(16, 30))),
                             ("/ore 14.00 - 16.30", (2.5, time(14), time(16, 30))),
                             ("/ore 9-11 verificatore", (2, time(9), time(11))),
                             ("/ore 22:00-24:00", (2, time(22), time(0))),
                             ("/ore 23:30–00:30 2026-11-04", (1, time(23, 30), time(0, 30)))]:
            esito = self.esito(riga)
            self.assertNotIsInstance(esito, str, riga)
            self.assertEqual((esito[0], esito[4], esito[5]), atteso, riga)
        self.assertEqual(self.esito("/ore 9-11 verificatore")[1], "Verificatore")
        self.assertEqual(self.esito("/ore 14:00-16:30")[1], "Responsabile")   # ruolo dello sprint
        self.assertEqual(self.esito("/ore 23:30-00:30 2026-11-04")[2], date(2026, 11, 4))
        # interpreta (usata finora) restituisce sempre 4 valori
        self.assertEqual(len(interpreta("/ore 14:00-16:30", self.GIORNO, "spagnoli", CONF)), 4)

    def test_errori_orario(self):
        for riga, motivo in [("/ore 25:00-26:00", "non è un orario"), ("/ore 14:70-15:00", "non è un orario"),
                             ("/ore 14:00-14:00", "coincidono"), ("/ore 16:00-14:00", "al massimo"),
                             ("/ore 14:00-16:30 boh", "non capisco"), ("/ore 14:00", "non è un orario")]:
            self.assertIn(motivo, self.esito(riga), riga)

    def test_orario_dopo_il_commento(self):
        self.assertIn("finisce dopo", self.esito("/ore 14:00-16:30", ora=time(15, 0)))
        self.assertNotIsInstance(self.esito("/ore 14:00-16:30", ora=time(16, 50)), str)   # margine
        self.assertNotIsInstance(self.esito("/ore 14:00-16:30 2026-11-04", ora=time(15, 0)), str)
        # a cavallo della mezzanotte, scritto dopo mezzanotte senza data: giorno prima
        esito = self.esito("/ore 23:00-00:30", ora=time(0, 45), giorno=date(2026, 11, 6))
        self.assertEqual(esito[2], date(2026, 11, 5))

    def test_vecchia_e_nuova_forma_insieme(self):
        # 19:00Z = 20:00 a Roma
        voci, scarti = voci_da_commenti([commento("gaexxx", "/ore 2\n/ore 14:00-16:30", id_="A")],
                                        "docs#1", CONF)
        self.assertEqual(scarti, [])
        self.assertEqual([(v.ore, v.orario, v.scritto_il) for v in voci],
                         [(2, "", self.GIORNO), (2.5, "14:00–16:30", self.GIORNO)])
        _, scarti = voci_da_commenti([commento("gaexxx", "/ore 20:00-22:00", id_="B")], "docs#1", CONF)
        self.assertIn("finisce dopo", scarti[0].motivo)

    def voci_di_prova(self):
        commenti = [
            commento("gaexxx", "/ore 14:00-16:30", "2026-11-05T19:00:00Z", id_="A"),
            # si sovrappone dalle 16:00 alle 16:30 (in un'altra issue)
            commento("gaexxx", "/ore 16:00-18:00 verificatore", "2026-11-05T19:30:00Z", id_="B"),
            commento("gaexxx", "/ore 18:00-19:00", "2026-11-05T19:30:00Z", id_="C"),  # attaccato: ok
            commento("gaexxx", "/ore 4", "2026-11-05T21:00:00Z", id_="D"),            # totale 9,5 > 8
            commento("gaexxx", "/ore 9-10 2026-11-02", "2026-11-06T10:00:00Z", id_="E"),  # 4 giorni dopo
            commento("alec0r", "/ore 14:00-16:30", "2026-11-05T19:00:00Z", id_="F"),  # altra persona
        ]
        voci = voci_da_commenti(commenti[:1], "docs#1", CONF)[0]
        voci += voci_da_commenti(commenti[1:], "docs#2", CONF)[0]
        return voci

    def test_controlli(self):
        segnalazioni = controlla(self.voci_di_prova(), CONF)
        self.assertEqual([s.tipo for s in segnalazioni],
                         ["Intervalli sovrapposti", "Troppe ore in un giorno", "Ore segnate in ritardo"])
        testi = " ".join(s.testo for s in segnalazioni)
        for pezzo in ["14:00–16:30 (docs#1) e 16:00–18:00 (docs#2)", "9,5 ore", "4 giorni dopo"]:
            self.assertIn(pezzo, testi)

    def test_riepilogo_cruscotto_e_csv(self):
        voci = self.voci_di_prova()
        testo = ore.riepilogo(voci, [], CONF)
        for pezzo in ["| Orario |", "| 14:00–16:30 |", "| — |", "Da controllare",
                      "Intervalli sovrapposti", "/ore 14:00-16:30"]:
            self.assertIn(pezzo, testo)
        analisi = Analisi(CONF, DatiProject("P", [], voci, []), date(2026, 11, 20))
        tipi = [a.tipo for a in analisi.anomalie]
        for tipo in ["Intervalli sovrapposti", "Troppe ore in un giorno", "Ore segnate in ritardo"]:
            self.assertEqual(tipi.count(tipo), 1, tipo)
        csv = registro_csv(analisi)
        self.assertIn("orario,scritto_il", csv.splitlines()[0])
        self.assertIn("14:00-16:30,2026-11-05", csv)

    def test_niente_segnalazioni_con_ore_normali(self):
        voci, _ = voci_da_commenti([commento("gaexxx", "/ore 2\n/ore 9-11\n/ore 14:00-16:30", id_="A")],
                                   "docs#1", CONF)
        self.assertEqual(controlla(voci, CONF), [])
        self.assertNotIn("Da controllare", ore.riepilogo(voci, [], CONF))


class Configurazione(unittest.TestCase):
    def test_errori_di_configurazione(self):
        base = (QUI / "esempio-pianificazione.toml").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as d:
            sbagliato = Path(d) / "p.toml"
            sbagliato.write_text(base.replace("biasini    = { Analista = 10 }", "biasini = { Cuoco = 10 }"),
                                 encoding="utf-8")
            with self.assertRaises(ErroreConfigurazione):
                carica_configurazione(sbagliato)


class Cruscotto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dati = leggi(CONF, da_file=QUI / "esempio-dati.json")
        cls.analisi = Analisi(CONF, cls.dati, date(2026, 11, 20))

    def test_ore_lette(self):
        self.assertEqual(len(self.dati.voci), 19)            # il commento della PR conta una volta
        self.assertAlmostEqual(self.analisi.ore(persona="guglielmo"), 6.5)
        self.assertAlmostEqual(self.analisi.ore(sprint=1), 20.5)
        self.assertAlmostEqual(self.analisi.ore(sprint=2), 12)

    def test_anomalie(self):
        tipi = [a.tipo for a in self.analisi.anomalie]
        self.assertEqual(tipi.count("Comando /ore non valido"), 2)
        self.assertEqual(tipi.count("Ruolo non pianificato"), 2)
        self.assertEqual(tipi.count("Issue chiusa senza ore"), 1)

    def test_obiettivi(self):
        stati = self.analisi.stato_obiettivi(CONF.sprint[0])
        self.assertEqual([s.raggiunto for s in stati], [True, False, None])

    def test_file_generati(self):
        with tempfile.TemporaryDirectory() as d:
            esito = cruscotto.main(["--uscita", d, "--da-file", str(QUI / "esempio-dati.json"),
                                    "--oggi", "2026-11-20"])
            self.assertEqual(esito, 0)
            for nome in ["README.md", "profile/README.md", "dati/ore.csv", "diario/sprint-1.md",
                         "tabelle/preventivo-sprint-1.tex", "tabelle/consuntivo-sprint-1.tex",
                         "tabelle/riepilogo-ruoli.tex"]:
                self.assertTrue((Path(d) / nome).exists(), nome)
            testo = (Path(d) / "README.md").read_text(encoding="utf-8")
            self.assertIn("Sprint 2", testo)
            self.assertIn("11.250,00 €", testo)
            # "Assegnata a" con nome e cognome (due Francesco nel gruppo)
            riga = next(r for r in testo.splitlines() if "docs#80" in r and "In Progress" in r)
            self.assertIn("| Luca Cesco Bolla |", riga)


class FintoGitHub:
    """Risponde alle query come farebbe GitHub, con dati inventati."""

    def __init__(self, nodi: dict):
        self.nodi = nodi                 # numero -> nodo issue/PR
        self.chiamate = []

    def query(self, testo, **v):
        self.chiamate.append((testo, v))
        if "issueOrPullRequest" in testo:
            return {"repository": {"issueOrPullRequest": self.nodi[v["numero"]]}}
        if "projectV2(number" in testo and "fields" in testo:
            return {"organization": {"projectV2": {"id": "P", "title": "GIT PUSH TEAM", "fields": {"nodes": [
                {"id": "F_ORE", "name": "Ore effettive", "dataType": "NUMBER"},
                {"id": "F_STIMA", "name": "Ore stimate", "dataType": "NUMBER"},
                {"id": "F_RUOLO", "name": "Ruolo", "dataType": "SINGLE_SELECT",
                 "options": [{"id": f"R_{r}", "name": r} for r in ["Analista", "Verificatore"]]},
                {"id": "F_STATO", "name": "Status", "dataType": "SINGLE_SELECT",
                 "options": [{"id": "S_todo", "name": "Todo"}, {"id": "S_rev", "name": "In Review"}]},
                {"id": "F_SPRINT", "name": "Sprint", "dataType": "ITERATION", "configuration": {
                    "iterations": [{"id": "IT2", "title": "Sprint 2", "startDate": "2026-11-16", "duration": 14}],
                    "completedIterations": [{"id": "IT1", "title": "Sprint 1", "startDate": "2026-11-02",
                                             "duration": 14}]}},
            ]}}}}
        if "addProjectV2ItemById" in testo:
            return {"addProjectV2ItemById": {"item": {"id": "NUOVO"}}}
        if "node(id:" in testo and "closingIssuesReferences" in testo:
            return {"node": self.nodi["pr"]}
        if "node(id:" in testo:
            return {"node": self.nodi["issue"]}
        return {}

    def mutazioni(self, nome):
        return [v for t, v in self.chiamate if nome in t]


class ComandoOreSuGitHub(unittest.TestCase):
    def test_ricalcolo_e_riepilogo(self):
        issue = {"__typename": "Issue", "id": "I1", "number": 7, "title": "T", "url": "u",
                 "repository": {"nameWithOwner": "Git-Push-Team/docs"},
                 "comments": {"nodes": [commento("alec0r", "/ore 2", id_="A"),
                                        commento("alec0r", "/ore xx", id_="B")]},
                 "projectItems": {"nodes": [{"id": "ITEM", "project": {"id": "P"}}]},
                 "closedByPullRequestsReferences": {"nodes": [
                     {"id": "PR9", "number": 9, "url": "u", "repository": {"nameWithOwner": "Git-Push-Team/docs"},
                      "comments": {"nodes": [commento("itsluca57", "/ore 1 verificatore", id_="Z")]}}]}}
        gh = FintoGitHub({7: issue})
        evento = {"action": "created", "repository": {"full_name": "Git-Push-Team/docs"},
                  "issue": {"number": 7},
                  "comment": {"node_id": "B", "body": "/ore xx", "created_at": "2026-11-05T19:00:00Z",
                              "user": {"login": "alec0r", "type": "User"}, "html_url": "u"}}
        ore.gestisci(gh, CONF, evento)
        campo = gh.mutazioni("updateProjectV2ItemFieldValue")[0]
        self.assertEqual((campo["i"], campo["f"], campo["v"]), ("ITEM", "F_ORE", {"number": 3.0}))
        corpo = gh.mutazioni("addComment")[0]["corpo"]
        self.assertIn("Ore registrate: 3", corpo)
        self.assertIn("non validi", corpo)
        self.assertEqual(gh.mutazioni("addReaction")[0]["r"], "CONFUSED")


class RiepilogoAZero(unittest.TestCase):
    def test_commenti_cancellati(self):
        """Cancellati tutti i /ore, il riepilogo esistente torna a 0 ore."""
        vecchio = commento("bot", "<!-- riepilogo-ore -->\n### Ore registrate: 0,5", bot=True, id_="R")
        issue = {"__typename": "Issue", "id": "I1", "number": 7, "title": "T", "url": "u",
                 "repository": {"nameWithOwner": "Git-Push-Team/docs"},
                 "comments": {"nodes": [vecchio]},
                 "projectItems": {"nodes": [{"id": "ITEM", "project": {"id": "P"}}]},
                 "closedByPullRequestsReferences": {"nodes": []}}
        gh = FintoGitHub({7: issue})
        evento = {"action": "deleted", "repository": {"full_name": "Git-Push-Team/docs"},
                  "issue": {"number": 7}, "comment": {"node_id": "X", "body": "/ore 0,5"}}
        ore.gestisci(gh, CONF, evento)
        self.assertEqual(gh.mutazioni("updateProjectV2ItemFieldValue")[0]["v"], {"number": 0.0})
        aggiornato = gh.mutazioni("updateIssueComment")[0]
        self.assertEqual(aggiornato["id"], "R")
        self.assertIn("Ore registrate: 0", aggiornato["corpo"])
        self.assertEqual(gh.mutazioni("addComment"), [])


class CollegamentoProject(unittest.TestCase):
    def test_issue_aperta(self):
        gh = FintoGitHub({"issue": {"id": "I1", "number": 5, "title": "T", "projectItems": {"nodes": []}}})
        corpo = "### Documento\n\nNorme\n\n### Ruolo\n\nVerificatore\n\n### Stima in ore\n\n3,5\n"
        evento = {"action": "opened", "issue": {"node_id": "I1", "number": 5, "body": corpo}}
        conf = carica_configurazione()
        conf.oggi = lambda: date(2026, 11, 20)
        progetto.issue_aperta(gh, conf, evento)
        valori = {v["f"]: v["v"] for v in gh.mutazioni("updateProjectV2ItemFieldValue")}
        self.assertEqual(valori["F_RUOLO"], {"singleSelectOptionId": "R_Verificatore"})
        self.assertEqual(valori["F_STIMA"], {"number": 3.5})
        self.assertEqual(valori["F_SPRINT"], {"iterationId": "IT2"})

    def test_pr_aperta(self):
        gh = FintoGitHub({"pr": {"id": "PR1", "number": 9, "title": "P", "projectItems": {"nodes": []},
                                 "closingIssuesReferences": {"nodes": [
                                     {"id": "I1", "number": 5, "title": "T",
                                      "projectItems": {"nodes": [{"id": "ITEM5", "project": {"id": "P"}}]}}]}}})
        evento = {"pull_request": {"node_id": "PR1", "number": 9, "draft": False}}
        progetto.pr_aperta(gh, CONF, evento)
        valori = gh.mutazioni("updateProjectV2ItemFieldValue")
        self.assertEqual(valori[0]["i"], "ITEM5")
        self.assertEqual(valori[0]["v"], {"singleSelectOptionId": "S_rev"})


if __name__ == "__main__":
    unittest.main()