"""IO de arquivos com guard-rails de segurança para a pasta de output.

`clean_dir` recusa apagar qualquer caminho que não seja exatamente a OUTPUT_DIR
dedicada dentro de BASE_DIR — protege contra o risco do caminho fixo do script antigo.
"""
import os
import shutil

from config import BASE_DIR, OUTPUT_DIR


def clean_dir(path: str) -> None:
    """Limpa (rmtree + recria) a pasta de output, com proteções."""
    norm = os.path.abspath(path)
    if norm != os.path.abspath(OUTPUT_DIR):
        raise ValueError(f"Recusado: clean_dir só opera em _output (recebeu {norm})")
    if not norm.startswith(os.path.abspath(BASE_DIR) + os.sep):
        raise ValueError("Recusado: caminho fora do diretório da aplicação")
    if os.path.exists(norm):
        shutil.rmtree(norm)
    os.makedirs(norm, exist_ok=True)


def write_files(output_dir: str, files) -> None:
    """Materializa uma lista de GeneratedFile na estrutura de pacotes.

    `files` é iterável de objetos com `.rel_path` (ex: src/main/java/.../X.java)
    e `.content`.
    """
    for gf in files:
        dest = os.path.join(output_dir, gf.rel_path.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(gf.content)
