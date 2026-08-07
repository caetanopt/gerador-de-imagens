from pathlib import Path

path = Path(__file__).parent.parent / "app.py"
lines = path.read_text(encoding="utf-8").split("\n")

# linha 871 (1-indexed) = 'with st.spinner("A gerar imagens..."):' -> índice 870
with_idx = 870
assert 'with st.spinner("A gerar imagens...")' in lines[with_idx], lines[with_idx]

# linha 1112 (1-indexed) = última linha do corpo do with (o '}' do dict comprehension) -> índice 1111
body_end_idx = 1111
assert lines[body_end_idx].strip() == "}", lines[body_end_idx]

# linha 1114 (1-indexed) = 'if images:' -> índice 1113 (não deve ser tocada)
sentinel_idx = 1113
assert lines[sentinel_idx].strip() == "if images:", lines[sentinel_idx]

new_lines = []
new_lines.extend(lines[:with_idx])
new_lines.append("        try:")
new_lines.append("            " + lines[with_idx].strip())
for line in lines[with_idx + 1: body_end_idx + 1]:
    new_lines.append(("    " + line) if line.strip() else line)
new_lines.append("        except Exception as e:")
new_lines.append('            st.error(f"Não foi possível gerar as imagens: {e}")')
new_lines.append("            images = None")
new_lines.extend(lines[body_end_idx + 1:])

path.write_text("\n".join(new_lines), encoding="utf-8")
print("ok")
