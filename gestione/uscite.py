"""
uscite.py -- trasforma l'Analisi in file: il cruscotto (Markdown), le
tabelle LaTeX per il Piano di Progetto, i numeri per il diario di bordo e
il registro completo delle ore (CSV).
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from calcoli import Analisi
from comune import RUOLI, SIGLE, Sprint, data_breve, data_lunga, euro_testo, ore_testo
from metriche import calcola

ICONE_ESITO = {"ok": "🟢", "attenzione": "🟠", "": "⚪"}


def barra(valore: float, totale: float, lunghezza: int = 10) -> str:
    if totale <= 0:
        return "—"
    quota = valore / totale
    pieni = min(lunghezza, round(quota * lunghezza))
    segno = " ▲" if quota > 1 else ""
    return f"{'█' * pieni}{'░' * (lunghezza - pieni)} {quota * 100:.0f} %{segno}"


def periodo(s: Sprint) -> str:
    return f"{data_breve(s.inizio)} – {data_breve(s.fine)} {s.fine.year}"


def ruoli_testo(ruoli: dict[str, float]) -> str:
    return ", ".join(f"{r} {ore_testo(o)} h" for r, o in sorted(ruoli.items(), key=lambda x: -x[1])) or "—"


# ==========================================================================
#  Cruscotto (Markdown)
# ==========================================================================
def cruscotto(a: Analisi, aggiornato: datetime) -> str:
    c = a.conf
    r = ["# 📊 Cruscotto del Git Push Team", "",
         f"_Aggiornato il {data_lunga(aggiornato.date())} alle {aggiornato:%H:%M}. "
         f"Dati: GitHub Project «{a.dati.titolo}» e `pianificazione.toml` del repository "
         f"[.github](https://github.com/{c.organizzazione}/.github). Visibile solo ai membri._", ""]

    # ---- scadenze ----
    scadenze = [(n, d) for n, d in sorted(c.scadenze.items(), key=lambda x: x[1]) if d >= a.oggi]
    if scadenze:
        r.append(" · ".join(f"**{n}**: {data_lunga(d)} (tra {(d - a.oggi).days} giorni)" for n, d in scadenze))
        r.append("")

    # ---- sprint corrente ----
    s = a.sprint_corrente
    if s:
        giorno = (a.oggi - s.inizio).days + 1
        durata = (s.fine - s.inizio).days + 1
        r += [f"## 🏃 {s.nome} · {periodo(s)}", "",
              f"Giorno {giorno} di {durata} {barra(giorno, durata)}", ""]
        r += _obiettivi(a, s)
        r += ["### Persone", "", "| Persona | Ruolo pianificato | Ore svolte | Avanzamento |",
              "| --- | --- | --- | --- |"]
        for p in a.persone:
            pianificate = s.ore_pianificate(p)
            svolte = {ru: a.ore(sprint=s.numero, persona=p, ruolo=ru) for ru in RUOLI}
            svolte = {ru: o for ru, o in svolte.items() if o}
            totale = sum(svolte.values())
            r.append(f"| {c.membri[p].nome} | {ruoli_testo(s.ruoli.get(p, {}))} "
                     f"| {ruoli_testo(svolte) if svolte else '0 h'} | {barra(totale, pianificate)} |")
        tot_p = sum(s.ore_pianificate(p) for p in a.persone)
        tot_e = a.ore(sprint=s.numero)
        r += [f"| **Totale** | **{ore_testo(tot_p)} h** | **{ore_testo(tot_e)} h** | {barra(tot_e, tot_p)} |", ""]
        r += _attivita(a, s)
    else:
        r += ["## 🏃 Sprint", "", "Oggi non c'è uno sprint in corso: pianificatelo in `pianificazione.toml`.", ""]

    # ---- totale progetto ----
    prev = a.matrice_preventivo()
    eff = a.matrice_effettive()
    r += ["## 🧮 Ore del progetto rispetto al preventivo", "",
          "Ore consumate / ore preventivate per persona e ruolo.", "",
          "| Persona | " + " | ".join(RUOLI) + " | Totale | Residuo | Consumo |",
          "| --- | " + " | ".join("---:" for _ in RUOLI) + " | ---: | ---: | --- |"]
    for p in a.persone:
        celle = [f"{ore_testo(eff[p][ru])}/{ore_testo(prev[p][ru])}" for ru in RUOLI]
        tp, te = sum(prev[p].values()), sum(eff[p].values())
        r.append(f"| {c.membri[p].nome} | " + " | ".join(celle)
                 + f" | {ore_testo(te)}/{ore_testo(tp)} | {ore_testo(tp - te)} | {barra(te, tp)} |")
    pr, er = a.per_ruolo(prev), a.per_ruolo(eff)
    r.append("| **Totale** | " + " | ".join(f"**{ore_testo(er[ru])}/{ore_testo(pr[ru])}**" for ru in RUOLI)
             + f" | **{ore_testo(sum(er.values()))}/{ore_testo(sum(pr.values()))}** "
             f"| **{ore_testo(sum(pr.values()) - sum(er.values()))}** | {barra(sum(er.values()), sum(pr.values()))} |")
    r.append("")

    r += ["### Costi per ruolo", "", "| Ruolo | €/h | Preventivo | Consumato | Residuo | Consumo |",
          "| --- | ---: | ---: | ---: | ---: | --- |"]
    for ru in RUOLI:
        t = c.tariffe.get(ru, 0)
        r.append(f"| {ru} | {ore_testo(t)} | {euro_testo(pr[ru] * t)} | {euro_testo(er[ru] * t)} "
                 f"| {euro_testo((pr[ru] - er[ru]) * t)} | {barra(er[ru], pr[ru])} |")
    cp, ce = a.costo(prev), a.costo(eff)
    r += [f"| **Totale** | | **{euro_testo(cp)}** | **{euro_testo(ce)}** | **{euro_testo(cp - ce)}** "
          f"| {barra(ce, cp)} |", ""]

    # ---- andamento per sprint ----
    r += _andamento(a)

    # ---- metriche ----
    r += ["## 📏 Metriche", "",
          "Soglie provvisorie, da allineare al Piano di Qualifica (`gestione/metriche.py`).", "",
          "| | Codice | Metrica | Valore | Come si calcola |", "| --- | --- | --- | --- | --- |"]
    for m in calcola(a):
        r.append(f"| {ICONE_ESITO.get(m.esito, '⚪')} | {m.codice} | {m.nome} | {m.valore} | {m.descrizione} |")
    r.append("")

    # ---- anomalie ----
    r += ["## ⚠️ Da sistemare", ""]
    if a.anomalie:
        per_tipo: dict[str, list] = {}
        for x in a.anomalie:
            per_tipo.setdefault(x.tipo, []).append(x)
        for tipo, elenco in per_tipo.items():
            r.append(f"**{tipo}** ({len(elenco)})")
            r += [f"- {x.testo}" + (f" · [apri]({x.url})" if x.url else "") for x in elenco[:30]]
            if len(elenco) > 30:
                r.append(f"- … e altri {len(elenco) - 30}")
            r.append("")
    else:
        r += ["Niente: tutto in ordine. ✅", ""]

    # ---- diario di bordo ----
    r += ["## 📓 Per il diario di bordo", ""]
    for sp in [x for x in (a.ultimo_concluso, a.sprint_corrente) if x]:
        r += diario(a, sp).strip().splitlines()[2:] + [""]
    r += ["---", "",
          "Come si legge e come si aggiorna: README del repository "
          f"[.github](https://github.com/{c.organizzazione}/.github). "
          "Il cruscotto si rigenera ogni notte; per aggiornarlo subito: *Actions → Cruscotto → Run workflow*.", ""]
    return "\n".join(r)


def _obiettivi(a: Analisi, s: Sprint) -> list[str]:
    stati = a.stato_obiettivi(s)
    if not stati:
        return ["_Obiettivi dello sprint non ancora scritti in `pianificazione.toml`._", ""]
    r = ["### Obiettivi", ""]
    for st in stati:
        if st.raggiunto is None:
            icona, dettaglio = "◻️", " _(da valutare in retrospettiva)_"
        else:
            icona = "✅" if st.raggiunto else "⏳"
            parti = [f"{x} ✔" for x in st.chiuse] + [x for x in st.aperte] + [f"{x} ❓" for x in st.sconosciute]
            dettaglio = f" — {', '.join(parti)}"
        r.append(f"- {icona} {st.obiettivo.testo}{dettaglio}")
    return r + [""]


def _attivita(a: Analisi, s: Sprint) -> list[str]:
    elenco = a.attivita_dello_sprint(s)
    if not elenco:
        return []
    r = [f"### Attività dello sprint ({sum(x.chiusa for x in elenco)}/{len(elenco)} chiuse)", "",
         "| | Attività | Colonna | Ruolo | Assegnata a | Stimate | Effettive |",
         "| --- | --- | --- | --- | --- | ---: | ---: |"]
    for x in sorted(elenco, key=lambda x: (x.chiusa, x.rif)):
        eff = sum(v.ore for v in x.voci)
        chi = ", ".join(a.conf.membri[p].nome.split()[0] for p in x.assegnatari) or "—"
        stima = ore_testo(x.ore_stimate) if x.ore_stimate is not None else "—"
        titolo = x.titolo.replace("|", "\\|")
        r.append(f"| {'✅' if x.chiusa else '⏳'} | [{x.rif}]({x.url}) {titolo} | {x.colonna or '—'} "
                 f"| {x.ruolo or '—'} | {chi} | {stima} | {ore_testo(eff)} |")
    return r + [""]


def _andamento(a: Analisi) -> list[str]:
    sprint = a.sprint_iniziati + ([a.prossimo] if a.prossimo else [])
    if not sprint:
        return []
    r = ["## 📈 Andamento per sprint", "",
         "| Sprint | Periodo | Ore pianificate | Ore effettive | Scarto | Costo pianificato | Costo effettivo | Effettive cumulate |",
         "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    cumulate = 0.0
    for s in sprint:
        pian = a.matrice_pianificate(s)
        tp = sum(sum(x.values()) for x in pian.values())
        iniziato = s.inizio <= a.oggi
        te = a.ore(sprint=s.numero) if iniziato else 0.0
        cumulate += te
        stato = " (in corso)" if s.contiene(a.oggi) else "" if iniziato else " (prossimo)"
        r.append(f"| {s.nome}{stato} | {periodo(s)} | {ore_testo(tp)} "
                 f"| {ore_testo(te) if iniziato else '—'} "
                 f"| {(('+' if te - tp > 0 else '') + ore_testo(te - tp)) if iniziato and tp else '—'} "
                 f"| {euro_testo(a.costo(pian))} | {euro_testo(a.costo(a.matrice_effettive(s.numero))) if iniziato else '—'} "
                 f"| {ore_testo(cumulate) if iniziato else '—'} |")
    return r + [""]


# ==========================================================================
#  Diario di bordo
# ==========================================================================
def diario(a: Analisi, s: Sprint) -> str:
    """I numeri di uno sprint, pronti da copiare nelle diapositive."""
    c = a.conf
    concluso = s.fine < a.oggi
    stato = "concluso" if concluso else f"in corso, giorno {(a.oggi - s.inizio).days + 1}"
    tp = sum(s.ore_pianificate(p) for p in a.persone)
    te = a.ore(sprint=s.numero)
    elenco = a.attivita_dello_sprint(s)
    chiuse = [x for x in elenco if x.chiusa]
    r = [f"# Diario di bordo · {s.nome}", "",
         f"### {s.nome} ({periodo(s)}, {stato})", "",
         f"- **Ore**: {ore_testo(te)} svolte su {ore_testo(tp)} pianificate ({barra(te, tp)})",
         f"- **Costo**: {euro_testo(a.costo(a.matrice_effettive(s.numero)))} su "
         f"{euro_testo(a.costo(a.matrice_pianificate(s)))} pianificati",
         f"- **Attività**: {len(chiuse)} chiuse su {len(elenco)}"]
    stati = a.stato_obiettivi(s)
    if stati:
        valutabili = [x for x in stati if x.raggiunto is not None]
        r.append(f"- **Obiettivi**: {sum(1 for x in valutabili if x.raggiunto)} raggiunti su {len(valutabili)} "
                 "con issue collegate" + (f" (+{len(stati) - len(valutabili)} da valutare)"
                                         if len(valutabili) < len(stati) else ""))
        for x in stati:
            segno = "◻️" if x.raggiunto is None else "✅" if x.raggiunto else "❌" if concluso else "⏳"
            r.append(f"    - {segno} {x.obiettivo.testo}")
    per_ruolo = {ru: a.ore(sprint=s.numero, ruolo=ru) for ru in RUOLI}
    r.append("- **Ore per ruolo**: " + (", ".join(f"{ru} {ore_testo(o)}" for ru, o in per_ruolo.items() if o) or "—"))
    if chiuse:
        r.append("- **Fatto**: " + "; ".join(f"{x.titolo} ({x.rif})" for x in chiuse[:12]))
    if not concluso:
        aperte = [x for x in elenco if not x.chiusa]
        if aperte:
            r.append("- **In corso**: " + "; ".join(f"{x.titolo} ({x.rif})" for x in aperte[:12]))
    if concluso and a.prossimo:
        r.append(f"- **Prossimo sprint** ({periodo(a.prossimo)}): "
                 + ("; ".join(o.testo for o in a.prossimo.obiettivi) or "obiettivi da definire"))
    return "\n".join(r) + "\n"


# ==========================================================================
#  Tabelle LaTeX per il Piano di Progetto
# ==========================================================================
INTESTAZIONE_TEX = ("% Generato da {org}/.github (gestione/cruscotto.py) il {giorno}.\n"
                    "% Non modificatelo a mano: si rigenera dai dati del Project e da\n"
                    "% gestione/pianificazione.toml.\n")


def _num(x: float) -> str:
    return ore_testo(x) if x else "--"


def _euro_tex(x: float) -> str:
    return euro_testo(x).replace(" €", "")


def _tabella_ruoli(a: Analisi, matrice: dict, didascalia: str, etichetta: str,
                   confronto: dict | None = None) -> str:
    """Persone per riga, ruoli per colonna; con confronto: 'effettive (scarto)'."""
    col = "l" + "r" * (len(RUOLI) + 1)
    righe = [r"\begin{table}[H]", r"  \centering", r"  \small",
             rf"  \caption{{{didascalia}\label{{{etichetta}}}}}",
             rf"  \begin{{tabular}}{{@{{}}{col}@{{}}}}", r"    \toprule",
             "    " + " & ".join([r"\intestazione{Membro}"] + [rf"\intestazione{{{SIGLE[ru]}}}" for ru in RUOLI]
                                 + [r"\intestazione{Totale}"]) + r" \\",
             r"    \midrule"]

    def cella(valore: float, previsto: float | None) -> str:
        if previsto is None:
            return _num(valore)
        if not valore and not previsto:
            return "--"
        scarto = valore - previsto
        segno = "" if not scarto else (rf" \scriptsize({'+' if scarto > 0 else '$-$'}{ore_testo(abs(scarto))})")
        return f"{ore_testo(valore)}{segno}"

    for p in a.persone:
        prev_p = confronto[p] if confronto else None
        celle = [cella(matrice[p][ru], prev_p[ru] if prev_p else None) for ru in RUOLI]
        tot = cella(sum(matrice[p].values()), sum(prev_p.values()) if prev_p else None)
        righe.append(rf"    \nome{{{p}}} & " + " & ".join(celle) + f" & {tot} " + r"\\")
    per_ruolo = a.per_ruolo(matrice)
    righe.append(r"    \midrule")
    righe.append(r"    \textbf{Totale ore} & " + " & ".join(_num(per_ruolo[ru]) for ru in RUOLI)
                 + f" & {_num(sum(per_ruolo.values()))} " + r"\\")
    righe.append(r"    \textbf{Costo (\texteuro)} & "
                 + " & ".join(_euro_tex(per_ruolo[ru] * a.conf.tariffe.get(ru, 0)) if per_ruolo[ru] else "--"
                              for ru in RUOLI)
                 + f" & {_euro_tex(a.costo(matrice))} " + r"\\")
    righe += [r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]
    return "\n".join(righe) + "\n"


def legenda() -> str:
    return ", ".join(f"{s} = {r}" for r, s in SIGLE.items())


def tabelle_latex(a: Analisi) -> dict[str, str]:
    """Nome del file -> contenuto."""
    testa = INTESTAZIONE_TEX.format(org=a.conf.organizzazione, giorno=a.oggi.isoformat())
    file = {}
    for s in a.conf.sprint:
        pian = a.matrice_pianificate(s)
        if not any(sum(x.values()) for x in pian.values()):
            continue
        file[f"preventivo-sprint-{s.numero}.tex"] = testa + _tabella_ruoli(
            a, pian, f"Preventivo dello {s.nome} ({s.inizio.isoformat()} -- {s.fine.isoformat()}): "
                     f"ore per membro e ruolo ({legenda()})", f"tab:preventivo-sprint-{s.numero}")
        if s.inizio <= a.oggi:
            stato = "" if s.fine < a.oggi else f", parziale al {a.oggi.isoformat()}"
            file[f"consuntivo-sprint-{s.numero}.tex"] = testa + _tabella_ruoli(
                a, a.matrice_effettive(s.numero),
                f"Consuntivo dello {s.nome} ({s.inizio.isoformat()} -- {s.fine.isoformat()}{stato}): "
                f"ore effettive per membro e ruolo, tra parentesi lo scarto dal preventivo",
                f"tab:consuntivo-sprint-{s.numero}", confronto=pian)

    prev, eff = a.matrice_preventivo(), a.matrice_effettive()
    file["preventivo-totale.tex"] = testa + _tabella_ruoli(
        a, prev, f"Preventivo complessivo del progetto: ore per membro e ruolo ({legenda()})",
        "tab:preventivo-totale")
    file["consuntivo-totale.tex"] = testa + _tabella_ruoli(
        a, eff, f"Ore consumate dall'inizio del progetto al {a.oggi.isoformat()}, per membro e ruolo "
                "(il residuo per ruolo è in Tabella~\\ref{tab:riepilogo-ruoli})", "tab:consuntivo-totale")

    # riepilogo per ruolo: preventivo, consumato, residuo, in ore e in euro
    pr, er = a.per_ruolo(prev), a.per_ruolo(eff)
    righe = [r"\begin{table}[H]", r"  \centering", r"  \small",
             rf"  \caption{{Ore e costi per ruolo al {a.oggi.isoformat()}: preventivo, consumato e "
             r"residuo\label{tab:riepilogo-ruoli}}",
             r"  \begin{tabular}{@{}lrrrrrr@{}}", r"    \toprule",
             r"    \intestazione{Ruolo} & \intestazione{Ore prev.} & \intestazione{Ore cons.} & "
             r"\intestazione{Ore res.} & \intestazione{Costo prev.} & \intestazione{Costo cons.} & "
             r"\intestazione{Costo res.} \\", r"    \midrule"]
    for ru in RUOLI:
        t = a.conf.tariffe.get(ru, 0)
        righe.append(f"    {ru} & {_num(pr[ru])} & {_num(er[ru])} & {_num(pr[ru] - er[ru])} & "
                     f"{_euro_tex(pr[ru] * t)} & {_euro_tex(er[ru] * t)} & {_euro_tex((pr[ru] - er[ru]) * t)} "
                     + r"\\")
    tp, te = sum(pr.values()), sum(er.values())
    righe += [r"    \midrule",
              rf"    \textbf{{Totale}} & {_num(tp)} & {_num(te)} & {_num(tp - te)} & "
              rf"{_euro_tex(a.costo(prev))} & {_euro_tex(a.costo(eff))} & {_euro_tex(a.costo(prev) - a.costo(eff))} \\",
              r"    \bottomrule", r"  \end{tabular}", r"\end{table}"]
    file["riepilogo-ruoli.tex"] = testa + "\n".join(righe) + "\n"
    return file


def leggimi_tabelle(nomi: list[str]) -> str:
    righe = ["# Tabelle per il Piano di Progetto", "",
             "Generate ogni notte dal cruscotto (`gestione/cruscotto.py` nel repository `.github`).",
             "Non modificatele a mano: si sovrascrivono.", "",
             "**Come usarle**: copiate i file che servono nella cartella del Piano di Progetto "
             "(per esempio `RTB/documenti/esterni/piano-di-progetto/tabelle/`) e includeteli con:", "",
             "```latex", r"\input{tabelle/consuntivo-sprint-1}", "```", "",
             "Usano `\\nome{...}` e `\\intestazione{...}` della classe `gpt.cls`.", "", "File:", ""]
    righe += [f"- `{n}`" for n in sorted(nomi)]
    return "\n".join(righe) + "\n"


# ==========================================================================
#  Registro completo delle ore (CSV, si apre con Excel o Google Fogli)
# ==========================================================================
def registro_csv(a: Analisi) -> str:
    uscita = io.StringIO()
    w = csv.writer(uscita)
    w.writerow(["data", "sprint", "chiave", "persona", "ruolo", "ore", "fuori_piano", "dove", "commento"])
    for v in sorted(a.dati.voci, key=lambda v: (v.giorno, v.persona)):
        w.writerow([v.giorno.isoformat(), v.sprint or "", v.persona, a.conf.membri[v.persona].nome, v.ruolo,
                    f"{v.ore:g}", "sì" if v.fuori_piano else "", v.fonte, v.url])
    return uscita.getvalue()
