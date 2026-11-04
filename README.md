# `.github` — gestione del Git Push Team

Questo repository speciale fa tre cose per tutta l'organizzazione:

1. **Pagina pubblica dell'organizzazione** (`profile/README.md`).
2. **Modelli comuni**: issue (*Attività*, *Bug*, *Riunione*), pull request,
   `CONTRIBUTING.md` e modelli di workflow. Valgono per ogni repository che
   non ha i propri (il repository `docs` ha i suoi).
3. **Gestione del progetto** (cartella `gestione/`):
   - il comando **`/ore`** per registrare le ore nei commenti delle issue;
   - il **collegamento automatico** di issue e PR al GitHub Project;
   - il **cruscotto** notturno: ore per persona e ruolo rispetto al
     preventivo, sprint, obiettivi, metriche, tabelle LaTeX per il Piano di
     Progetto e numeri per il diario di bordo.

```text
.github/
├── profile/README.md            pagina pubblica dell'organizzazione
├── CONTRIBUTING.md              come lavoriamo (in breve)
├── .github/
│   ├── ISSUE_TEMPLATE/          modelli di issue predefiniti
│   ├── pull_request_template.md
│   └── workflows/
│       ├── ore.yml              riutilizzabile: comando /ore
│       ├── progetto.yml         riutilizzabile: collegamento al Project
│       ├── cruscotto.yml        ogni notte: genera il cruscotto
│       └── prove.yml            prove automatiche degli script
├── workflow-templates/          i due workflow da copiare negli altri repository
└── gestione/
    ├── pianificazione.toml      ⭐ L'UNICO FILE DA COMPILARE: membri, preventivo, sprint
    ├── ore.py, progetto.py, cruscotto.py   i tre programmi
    ├── comune.py, bacheca.py, dati.py, registro_ore.py, calcoli.py, uscite.py
    ├── metriche.py              le metriche del cruscotto (da ampliare)
    └── test/                    prove con dati inventati
```

Il cruscotto viene scritto nel repository **privato** `.github-private`: il
suo `profile/README.md` compare sulla pagina dell'organizzazione **solo ai
membri**.

---

## Come funziona, in breve

```text
  pianificazione.toml ─────────────┐   (preventivo, sprint, ruoli, obiettivi)
                                   ▼
  commenti "/ore 2" ──► ore.py ──► Project ("Ore effettive") ──► cruscotto.py ──► .github-private
  issue / PR nuove ──► progetto.py ──► Project (Ruolo, Ore stimate, Sprint, In review)     ├ README (cruscotto)
                                                                                           ├ tabelle/*.tex
                                                                                           ├ diario/sprint-N.md
                                                                                           └ dati/ore.csv
```

- **La fonte delle ore sono i commenti `/ore`**, non il campo del Project: il
  campo "Ore effettive" è solo un totale comodo da vedere nella bacheca.
  Modificare o cancellare un commento corregge tutto.
- **La fonte del previsto è `pianificazione.toml`**: preventivo (dalla
  Dichiarazione di Impegni) e, per ogni sprint, date, obiettivi e ruoli con
  le ore pianificate di ognuno.

---

## Setup (una volta sola)

Servono i permessi di **owner** dell'organizzazione per i passi 1, 2 e 4.

### 1. Creare la GitHub App

Il bot agisce con una GitHub App dell'organizzazione: il token automatico
delle Actions non può leggere né scrivere i Project dell'organizzazione, e le
deploy key sono disabilitate.

1. Pagina dell'organizzazione → **Settings** → in fondo a sinistra
   **Developer settings** → **GitHub Apps** → **New GitHub App**.
2. Compilate:
   - **GitHub App name**: `Git Push Team Gestione` (deve essere unico su
     GitHub: se è preso, aggiungete qualcosa);
   - **Homepage URL**: `https://github.com/Git-Push-Team`;
   - **Webhook**: togliete la spunta da **Active**;
   - **Permissions → Repository permissions**:
     - *Contents*: **Read and write** (per scrivere il cruscotto in `.github-private`);
     - *Issues*: **Read and write** (commento di riepilogo, reazioni);
     - *Pull requests*: **Read and write** (commenti `/ore` nelle PR);
     - *Metadata*: Read-only (è già impostato);
   - **Permissions → Organization permissions**:
     - *Projects*: **Read and write**;
   - **Where can this GitHub App be installed?** → *Only on this account*.
3. **Create GitHub App**. Nella pagina che si apre copiate l'**App ID** (un numero).
4. Più in basso, **Private keys** → **Generate a private key**: si scarica un
   file `.pem`. Tenetelo al sicuro e non caricatelo in nessun repository.
5. Menu a sinistra **Install App** → **Install** accanto a *Git-Push-Team* →
   **All repositories** → **Install**.

### 2. Salvare App ID e chiave nell'organizzazione

Organizzazione → **Settings** → **Secrets and variables** → **Actions**:

1. scheda **Variables** → **New organization variable**: nome
   `GESTIONE_APP_ID`, valore l'App ID; *Repository access*: **All repositories**;
2. scheda **Secrets** → **New organization secret**: nome `GESTIONE_APP_KEY`,
   valore **tutto** il contenuto del file `.pem` (aprite il file con un editor
   di testo e copiate dalla riga `-----BEGIN` alla riga `-----END`, comprese);
   *Repository access*: **All repositories**.

> Con il piano gratuito di GitHub, segreti e variabili dell'organizzazione
> funzionano nei repository **pubblici** (`docs`, `.github`, `poc` lo sono).
> I workflow non girano mai nel repository privato `.github-private`: il bot
> ci scrive da fuori.

### 3. Preparare il GitHub Project

Nel Project **GIT PUSH TEAM** (⋯ in alto a destra → **Settings**):

1. **Campo Sprint**: **+ New field** → nome `Sprint` → tipo **Iteration** →
   *Starts on* **2026-11-02**, *Duration* **2 weeks** → **Save**. GitHub crea
   le prime iterazioni; le successive si aggiungono con **+ Add iteration**.
2. Controllate che ci siano, **con questi nomi esatti** (altrimenti cambiate
   i nomi in `gestione/pianificazione.toml`, sezione `[campi]`):
   - `Ore effettive` e `Ore stimate`, tipo **Number**;
   - `Ruolo`, tipo **Single select**, con le opzioni Responsabile,
     Amministratore, Analista, Progettista, Programmatore, Verificatore;
   - `Status` con una colonna **In review**.
3. ⋯ → **Workflows**: attivate **Item closed** (→ *Done*) e **Pull request
   merged** (→ *Done*). Così, quando la PR viene unita, la issue si chiude e
   finisce in *Done* da sola.
4. **Viste consigliate** (+ New view):
   - *Sprint corrente*: tipo **Board**, filtro `sprint:@current`;
   - *Ore*: tipo **Table**, raggruppata per **Sprint**, con *Field sum* su
     `Ore stimate` e `Ore effettive` (menu della vista → *Field sum*).

### 4. Creare i repository `.github` e `.github-private`

1. **`.github`**: Organizzazione → **New repository** → nome `.github` →
   **Public** → senza README → **Create**. In GitHub Desktop: *File → Clone
   repository* → `Git-Push-Team/.github`; copiate dentro tutti i file di
   questa cartella; *Commit to main* → *Push origin*.
2. **`.github-private`**: **New repository** → nome `.github-private` →
   **Private** → spuntate **Add a README file** (deve avere almeno un
   commit) → **Create**.
3. In `.github` → scheda **Actions**: il workflow **Prove** deve essere verde.

### 5. Compilare `gestione/pianificazione.toml`

È l'unico file da compilare (lo fa il Responsabile, con una PR):

- **ogni sprint**: un blocco `[[sprint]]` con `numero`, `inizio`, `fine`,
  `obiettivi` e la tabella `[sprint.ruoli]`, con ruolo e ore pianificate di
  ognuno:

  ```toml
  [[sprint]]
  numero = 1
  inizio = 2026-11-02
  fine = 2026-11-15
  obiettivi = [
    { testo = "Prima stesura delle Norme di Progetto", issue = ["docs#70"] },
    { testo = "Primo incontro di analisi con Eggon" },
  ]
  [sprint.ruoli]
  biasini  = { Analista = 10 }
  spagnoli = { Responsabile = 8, Verificatore = 2 }
  ```

  Un obiettivo con `issue` è raggiunto quando sono tutte chiuse; senza
  `issue` si valuta a mano in retrospettiva. Il ruolo con più ore è quello
  usato da `/ore` quando non si scrive il ruolo;
- **le scadenze** (`[scadenze]`), appena decidete la data dell'RTB;
- **il preventivo**, solo se cambia la Dichiarazione di Impegni.

Se il file ha un errore, il workflow **Prove** della PR diventa rosso e dice
quale riga sistemare.

### 6. Primo cruscotto

`.github` → **Actions** → **Cruscotto** → **Run workflow**. Dopo circa un
minuto:

- in `.github-private` compaiono `README.md`, `profile/README.md`,
  `tabelle/`, `diario/`, `dati/`;
- sulla pagina dell'organizzazione, da membri, si vede il cruscotto (in alto
  a destra c'è il selettore *View as: Member / Public*).

Da allora si aggiorna da solo ogni notte e ogni volta che cambia
`gestione/`.

### 7. Collegare gli altri repository

In ogni repository dove si lavora con le issue (`docs`, `poc`, poi `mvp`)
servono due file in `.github/workflows/`, uguali a quelli di
`workflow-templates/`:

- `ore.yml`: il comando `/ore`;
- `progetto.yml`: issue nel Project, PR → *In review*.

Si possono aggiungere anche da GitHub: nel repository, **Actions** → **New
workflow** → sezione *By Git-Push-Team* → **Configure** → **Commit**.

**Etichette**: i modelli di issue usano le etichette `attività`, `bug` e
`riunione`; se nel repository non esistono, GitHub le ignora. Createle una
volta per tutte in Organizzazione → **Settings** → **Repository defaults** →
*Repository labels* (valgono per i repository nuovi; in quelli esistenti
si creano da *Issues → Labels*).

### 8. Prova finale

1. In `poc`, aprite una issue con il modello **Attività** (ruolo
   Amministratore, stima 1). Entro un minuto è nel Project, con Ruolo, Ore
   stimate e Sprint compilati.
2. Scrivete un commento `/ore 0,5 amministratore`: arriva un 👍, compare il
   commento di riepilogo e nel Project *Ore effettive* diventa 0,5.
3. Modificate il commento in `/ore 0,25 amministratore`: il riepilogo e il
   Project si aggiornano.
4. Lanciate il **Cruscotto** a mano e controllate che la mezz'ora compaia.

---

## Uso quotidiano

| Chi | Quando | Cosa |
| --- | --- | --- |
| Tutti | mentre lavorano | `/ore 2` nei commenti della issue (o `/ore 1 verificatore` nella PR) |
| Tutti | a ogni riunione | una issue *Riunione*; ogni partecipante scrive `/ore 1,5` |
| Responsabile | all'inizio dello sprint | aggiunge lo sprint in `pianificazione.toml` (ruoli, ore, obiettivi) |
| Responsabile | alla retrospettiva | legge il cruscotto: ore, obiettivi, metriche, *Da sistemare* |
| Chi prepara il diario di bordo | ogni settimana | copia i numeri da `diario/sprint-N.md` in `.github-private` |
| Chi aggiorna il Piano di Progetto | a fine sprint | copia le tabelle da `.github-private/tabelle/` (o dall'artefatto del workflow) |

Le tabelle LaTeX usano `\nome{...}` e `\intestazione{...}` della classe
`gpt.cls` e si includono con `\input{tabelle/consuntivo-sprint-1}`.

## Ampliare le metriche

Le metriche sono in `gestione/metriche.py`: ognuna è una funzione che
restituisce codice, nome, valore, descrizione ed esito. Per aggiungerne una
(per esempio quelle del Piano di Qualifica): scrivete la funzione e
aggiungetela alla lista `METRICHE` in fondo al file. Le soglie attuali sono
provvisorie.

## Provare in locale

Serve Python 3.11 o più recente, senza altre librerie.

```bash
python3 -m unittest discover -s gestione/test -v          # prove automatiche
GESTIONE_CONFIGURAZIONE=gestione/test/esempio-pianificazione.toml \
  python3 gestione/cruscotto.py --uscita prova \
    --da-file gestione/test/esempio-dati.json --oggi 2026-11-20   # cruscotto con dati inventati
```

Il cruscotto di prova finisce nella cartella `prova/` (non caricatela).

## Se qualcosa non va

| Sintomo | Cosa controllare |
| --- | --- |
| Il workflow fallisce al passo *Token della GitHub App* | variabile `GESTIONE_APP_ID` e segreto `GESTIONE_APP_KEY` (passo 2), e che l'App sia installata (passo 1.5) |
| *Project n. 1 non trovato* | il numero del Project in `pianificazione.toml` e il permesso *Projects: Read and write* dell'App |
| *Nel Project manca il campo ...* | i nomi in `[campi]` di `pianificazione.toml` devono essere identici a quelli del Project |
| `/ore` non fa niente | il repository ha `.github/workflows/ore.yml`? (passo 7). Nella scheda *Actions* del repository c'è l'errore |
| 😕 sotto un commento `/ore` | il commento di riepilogo dice cosa non va (spesso: manca il ruolo perché lo sprint non è pianificato) |
| Il cruscotto non si aggiorna | `.github` → *Actions* → *Cruscotto*: leggete l'errore; il repository `.github-private` deve esistere e avere un commit |
| *Pianificazione incompleta* nel cruscotto | manca lo sprint di oggi o il ruolo di qualcuno in `pianificazione.toml` |
