"""Empacota os arquivos gerados num .zip em memória, refletindo a estrutura
de pacotes Java (cada entrada usa o rel_path do GeneratedFile)."""
import io
import zipfile


def build_zip(files) -> io.BytesIO:
    """Recebe iterável de GeneratedFile (.rel_path, .content) -> BytesIO do zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for gf in files:
            zf.writestr(gf.rel_path, gf.content)
    buf.seek(0)
    return buf
