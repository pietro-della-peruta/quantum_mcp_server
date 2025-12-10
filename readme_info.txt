Descrizione della Soluzione
-------------------------
La soluzione implementata consiste in un server MCP (Model Context Protocol) basato su Python che funge da interfaccia tra l'utente e la piattaforma IBM Quantum utilizzando la libreria Qiskit. 

Le caratteristiche principali includono:
1.  **Server MCP Qiskit**: Un server che espone strumenti per elencare i backend quantistici (`list_backends`) ed eseguire circuiti quantistici (`run_circuit`).
2.  **Gestione Intelligente dei Backend**: Il sistema tenta prima di connettersi ai backend reali o ai simulatori cloud di IBM Quantum. Se l'account utente non ha accesso a simulatori remoti (comune nei piani "Open"), il sistema effettua automaticamente il fallback su un simulatore locale (`basic_simulator`) per garantire che il codice funzioni sempre.
3.  **Algoritmo di Shor Corretto**: È stato fornito un esempio funzionante dell'algoritmo di Shor per fattorizzare il numero 15 (con a=7). Il codice include un circuito QASM pre-generato matematicamente corretto e una logica di post-elaborazione che analizza le misure più frequenti per ignorare i risultati banali (fase 0) e trovare i fattori corretti (3 e 5).

Passi per l'Utilizzo
-------------------

1.  **Prerequisiti**
    Assicurarsi di avere Python installato e un account IBM Quantum attivo. È necessario recuperare il proprio API Token dalla dashboard di IBM Quantum.

2.  **Configurazione dell'Ambiente**
    Il server richiede le librerie `qiskit`, `qiskit-ibm-runtime`, `mcp` e `python-dotenv`.
    
    Creare un file `.env` nella cartella `src/qiskit_mcp_server/` con il seguente contenuto:
    ```
    QISKIT_IBM_TOKEN=il_tuo_token_qui
    ```

3.  **Installazione delle Dipendenze**
    Eseguire il comando nella root del progetto:
    ```bash
    pip install -e .
    ```
    (Assicurarsi di aver attivato l'ambiente virtuale se in uso).

4.  **Generazione del Circuito (Opzionale)**
    Il file QASM corretto è già incluso (`shor_15_7.qasm`). Se necessario, può essere rigenerato con:
    ```bash
    python generate_shor_qasm.py > shor_15_7.qasm
    ```

5.  **Esecuzione dell'Esempio**
    Per avviare l'algoritmo di Shor tramite il server MCP, eseguire:
    ```bash
    python shor_example.py
    ```

6.  **Interpretazione dei Risultati**
    Lo script avvierà il server MCP, si connetterà a IBM (o userà il fallback locale), eseguirà il circuito e mostrerà le chiavi di misura.
    Cercare nell'output la riga:
    `-> SUCCESS! Factors of 15 are 3 and 5`
    
    Nota: L'algoritmo è probabilistico. Se non trova i fattori al primo tentativo, riprovare l'esecuzione.
