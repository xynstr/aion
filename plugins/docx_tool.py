from docx import Document

def create_docx_func(params, memory):
    """Erstellt eine neue .docx-Datei mit dem angegebenen Inhalt."""
    path = params.get('path')
    content = params.get('content', '')

    if not path:
        return {'error': 'Path is required'}

    try:
        document = Document()
        if content:
            document.add_paragraph(content)
        document.save(path)
        return {'ok': True, 'saved': True, 'path': path}
    except Exception as e:
        return {'error': str(e)}

def register(api):
    """Registriert das create_docx Tool."""
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Der vollständige Pfad zur neuen .docx-Datei."
            },
            "content": {
                "type": "string",
                "description": "Der Textinhalt der Datei."
            }
        },
        "required": ["path"]
    }
    
    api.register_tool(
        name="create_docx",
        description="Erstellt eine neue .docx-Datei mit dem angegebenen Inhalt.",
        func=create_docx_func,
        input_schema=input_schema
    )