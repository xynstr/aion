def register(api):
    import difflib
    from pathlib import Path

    def smart_patch(path: str = "", old_block: str = "", new_block: str = "", context_lines: int = 3, **_):
        path = Path(path)
        context_lines = int(context_lines)
        if not path.is_file():
            return {'ok': False, 'error': f'Datei nicht gefunden: {path}'}
        orig = path.read_text(encoding='utf-8', errors='replace')
        orig_lines = orig.splitlines(keepends=True)

        block_lines = old_block.strip().splitlines()
        # Stripped-Versionen für den Vergleich — aber wir tracken die echten Zeilenpositionen
        block_core = [l.strip() for l in block_lines if l.strip()]

        # Suche: finde den echten Zeilenbereich der dem block_core entspricht
        match_start = -1
        match_end   = -1
        for i in range(len(orig_lines)):
            # Sammle nicht-leere stripped Zeilen ab Position i bis wir block_core abgedeckt haben
            collected = []
            j = i
            while j < len(orig_lines) and len(collected) < len(block_core):
                s = orig_lines[j].strip()
                if s:
                    collected.append(s)
                j += 1
            if collected == block_core:
                match_start = i
                match_end   = j  # exklusiv
                break

        if match_start == -1:
            # Fuzzy-Fallback via difflib
            norm_orig  = '\n'.join(l.strip() for l in orig_lines if l.strip())
            norm_block = '\n'.join(block_core)
            s = difflib.SequenceMatcher(None, norm_orig, norm_block)
            match = s.find_longest_match(0, len(norm_orig), 0, len(norm_block))
            if match.size < len(norm_block) // 2:
                return {'ok': False, 'error': 'Zielblock nicht gefunden (auch fuzzy). Genaueren Kontext angeben.'}
            # Zeile im Original schätzen
            approx_line = norm_orig[:match.a].count('\n')
            match_start = approx_line
            match_end   = min(approx_line + len(block_core), len(orig_lines))

        # Eindeutigkeits-Check: zweiten Treffer suchen
        second = -1
        for i in range(match_start + 1, len(orig_lines)):
            collected = []
            j = i
            while j < len(orig_lines) and len(collected) < len(block_core):
                s = orig_lines[j].strip()
                if s:
                    collected.append(s)
                j += 1
            if collected == block_core:
                second = i
                break
        if second != -1:
            return {'ok': False, 'error': f'Zielblock mehrdeutig — kommt mindestens 2x vor (Zeilen {match_start+1} und {second+1}). Mehr Kontext angeben.'}

        # Patch anwenden
        pre  = orig_lines[max(0, match_start - context_lines):match_start]
        post = orig_lines[match_end:match_end + context_lines]
        new_lines = [l + '\n' for l in new_block.strip().splitlines()]
        patched = (
            orig_lines[:max(0, match_start - context_lines)]
            + pre + new_lines + post
            + orig_lines[match_end + context_lines:]
        )
        path.write_text(''.join(patched), encoding='utf-8')
        return {
            'ok': True,
            'patch_applied': True,
            'at_line': match_start + 1,
            'replaced_lines': f'{match_start + 1}–{match_end}',
            'pre_context': ''.join(pre),
            'post_context': ''.join(post),
        }

    api.register_tool(
        name='smart_patch',
        description=(
            'Kontextsensitive, robuste Code-Patches (Whitespace-tolerant, fuzzy, Eindeutigkeits-Check). '
            'Bevorzuge file_replace_lines wenn du Zeilennummern kennst.'
        ),
        func=smart_patch,
        input_schema={
            'type': 'object',
            'properties': {
                'path':          {'type': 'string'},
                'old_block':     {'type': 'string'},
                'new_block':     {'type': 'string'},
                'context_lines': {'type': 'integer'},
            },
            'required': ['path', 'old_block', 'new_block'],
        },
    )
