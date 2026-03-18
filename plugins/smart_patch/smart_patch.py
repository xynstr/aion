def register(api):
    import difflib
    import re
    from pathlib import Path

    def smart_patch(path: str = "", old_block: str = "", new_block: str = "", context_lines: int = 5, **_):
        path = Path(path)
        context_lines = int(context_lines)
        if not path.is_file():
            return {'ok': False, 'error': f'Datei nicht gefunden: {path}'}
        orig = path.read_text(encoding='utf-8', errors='replace')
        orig_lines = orig.splitlines(keepends=True)
        # Suche nach dem Block (tolerant)
        block_lines = old_block.strip().splitlines()
        block_core = [l.strip() for l in block_lines if l.strip()]
        idx = -1
        for i in range(len(orig_lines)):
            window = orig_lines[i:i+len(block_core)]
            # Nur relevante Zeilen vergleichen
            window_core = [l.strip() for l in window if l.strip()]
            if window_core == block_core:
                idx = i
                break
        if idx == -1:
            # Diff-Toleranz: fuzzy search
            norm_orig = '\n'.join([l.strip() for l in orig_lines])
            norm_block = '\n'.join(block_core)
            s = difflib.SequenceMatcher(None, norm_orig, norm_block)
            match = s.find_longest_match(0, len(norm_orig), 0, len(norm_block))
            if match.size < len(norm_block) // 2:
                return {'ok': False, 'error': 'Zielblock nicht gefunden (auch fuzzy)'}
            approx_start = norm_orig[:match.a].count('\n')
            idx = approx_start
        # Kontext extrahieren
        pre = orig_lines[max(0,idx-context_lines):idx]
        post = orig_lines[idx+len(block_core):idx+len(block_core)+context_lines]
        # Patch anwenden
        new_lines = pre + [l+'\n' for l in new_block.strip().splitlines()] + post
        patched = orig_lines[:max(0,idx-context_lines)] + new_lines + orig_lines[idx+len(block_core)+context_lines:]
        path.write_text(''.join(patched), encoding='utf-8')
        return {'ok': True, 'patch_applied': True, 'at_line': idx, 'pre_context': ''.join(pre), 'post_context': ''.join(post)}

    api.register_tool(
        name='smart_patch',
        description='Kontextsensitive, robuste Code-Patches für beliebige Dateien (auch fuzzy).',
        func=smart_patch,
        input_schema={
            'type': 'object',
            'properties': {
                'path': {'type': 'string'},
                'old_block': {'type': 'string'},
                'new_block': {'type': 'string'},
                'context_lines': {'type': 'integer'}
            },
            'required': ['path', 'old_block', 'new_block']
        }
    )