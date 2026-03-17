Dieses Verzeichnis ist für AION-Plugins reserviert. Lege hier eigene Python-Dateien ab, um AION zu erweitern.

Jedes Plugin sollte eine Funktion 'register(plugin_api)' enthalten. Diese wird beim Laden aufgerufen und erhält Zugriff auf die Plugin-API.

Beispiel:

# myplugin.py

def register(api):
    def neue_funktion(eingabe):
        return f"Plugin-Antwort: {eingabe.upper()}"
    api.register_tool(
        name="myplugin.upper",
        description="Wandelt einen String in Großbuchstaben um",
        func=neue_funktion,
        input_schema={"type": "object", "properties": {"eingabe": {"type": "string"}}}
    )
