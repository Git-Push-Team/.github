# Come lavoriamo

Regole comuni a tutti i repository del Git Push Team. Le regole complete
sono nelle **Norme di Progetto**; per la documentazione c'è anche la
[GUIDA del repository docs](https://github.com/Git-Push-Team/docs/blob/main/GUIDA.md).

## Il giro di ogni attività

1. **Issue.** Ogni lavoro parte da una issue (modelli *Attività*, *Bug*,
   *Riunione*), con ruolo e stima in ore. Entra da sola nel
   [Project](https://github.com/orgs/Git-Push-Team/projects/1), nello sprint
   in corso. Assegnatela a voi stessi.
2. **Branch.** Un branch per issue, a partire da `main` aggiornato:
   `tipo/numero-due-parole`, per esempio `feat/12-login`, `fix/15-crash-avvio`,
   `poc/8-rubyllm`, `doc/20-verbale`.
3. **Commit.** Piccoli e con un messaggio che dice cosa cambia, in italiano:
   `Aggiunge il controllo della sessione`.
4. **Pull request.** Con `Closes #numero` nella descrizione: la issue passa in
   *In review*. Come revisore il Verificatore, diverso dall'autore.
5. **Verifica e merge.** Il Verificatore controlla, approva e unisce. La issue
   si chiude e va in *Done*.

`main` è protetto: si cambia solo con una PR approvata da un'altra persona.

## Le ore: il comando `/ore`

Mentre lavorate, scrivete nei commenti della issue (o della PR che la chiude)
quante ore ci avete dedicato:

| Commento | Significato |
| --- | --- |
| `/ore 2` | 2 ore, nel ruolo che avete nello sprint in corso |
| `/ore 1,5 verificatore` | 1 ora e mezza da Verificatore |
| `/ore 1h30 analista 2026-11-05` | lavoro fatto in un altro giorno |
| `/ore 45m` | 45 minuti |

- Le ore sono sempre di **chi scrive il commento**: nessuno le segna per un altro.
- Più righe `/ore` nello stesso commento vanno bene.
- **Per correggere** si modifica o si cancella il commento: il totale si ricalcola.
- Il bot mette 👍 se il comando è valido, 😕 se c'è un errore, e tiene
  aggiornato un commento di riepilogo nella issue.
- **Riunioni**: ogni riunione ha la sua issue (modello *Riunione*) e ogni
  partecipante ci scrive le sue ore.
- **Verifica**: il Verificatore scrive `/ore ... verificatore` nella PR; le ore
  vanno alla issue che la PR chiude.

Il riepilogo di tutto (ore per persona e ruolo, preventivo, sprint, metriche)
è nel cruscotto, visibile ai membri sulla pagina dell'organizzazione.
