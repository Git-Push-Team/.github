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
from datetime import date
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
from registro_ore import interpreta, leggi_ore, voci_da_commenti  # noqa: E402

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
