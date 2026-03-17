def register(api):
    import random
    
    def clio_check(input: dict):
        """
        Führt einen CLIO-Reflexionszyklus aus: Ansatz, Konfidenzbewertung, ggf. weiter zerlegen, Meta-Check.
        Erwartet input: {
            'nutzerfrage': str,           # Die aktuelle Nutzerfrage oder Aufgabe
            'letzte_antwort': str = '',  # Optional: letzte Antwort von AION
            'force': bool = False        # Falls True, wird der Zyklus erzwungen, sonst nur auf expliziten Aufruf
        }
        """
        frage = input.get('nutzerfrage', '').strip()
        letzte_antwort = input.get('letzte_antwort', '').strip()
        force = bool(input.get('force', False))
        # 1. Lösungsansatz formulieren
        ansatz = f"Ich werde zunächst recherchieren, welche Faktoren für diese Aufgabe relevant sind und sie ggf. in Teilschritte zerlegen."
        # (In Realität sollte dies KI-generiert sein, hier als Platzhalter)
        # 2. Konfidenz bewerten (Simulation, z.B. Zufallswert, in echter KI-Integration LLM-basiert)
        konfidenz = random.randint(40, 95)
        # 3. Begründung
        begruendung = "Ich bin eher unsicher, weil die Aufgabenstellung unklar ist und externe Informationen gebraucht werden." if konfidenz < 70 else "Ich bin ziemlich sicher, weil ich dieses Problem schon oft gelöst habe."
        clio_summary = f"# clio-check:\nAnsatz: {ansatz}\nKonfidenz: {konfidenz}. Begründung: {begruendung}"
        # 4. Meta-Check nach Antwort
        if letzte_antwort:
            krit_annahme = "Dass die gefundene Information aktuell und korrekt ist."
            alt_antwort = "Falls das nicht stimmt, müsste die Lösung aktualisiert oder ein anderer Ansatz gewählt werden."
            meta_summary = f"# meta-check:\nKritische Annahme: {krit_annahme}. Falls falsch: {alt_antwort}"
        else:
            meta_summary = ""
        # Steuer-Logik — reflect wird vom LLM automatisch über den System-Prompt aufgerufen
        return {
            'next':      'continue_work' if konfidenz < 70 else 'answer',
            'clio':      clio_summary,
            'meta':      meta_summary,
            'konfidenz': konfidenz,
        }
    
    api.register_tool(
        name='clio_check',
        description='Führt einen CLIO-Zyklus aus: Ansatz, Konfidenz, ggf. weiterdenken, Meta-Check.',
        func=clio_check,
        input_schema={
            'type': 'object',
            'properties': {
                'nutzerfrage': {'type': 'string'},
                'letzte_antwort': {'type': 'string'},
                'force': {'type': 'boolean'}
            },
            'required': ['nutzerfrage']
        }
    )