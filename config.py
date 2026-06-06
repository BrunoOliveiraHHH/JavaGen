"""Configuração central do JavaGen.

Caminhos derivados do diretório onde a aplicação roda (nunca caminho fixo
externo), corrigindo o risco do `D:\\Projects\\JavaGen` hardcoded do script antigo.
"""
import os

# Diretório onde este arquivo (e a app) vive.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Pasta dedicada e descartável para materializar os arquivos gerados.
# Prefixo "_" deixa claro que é volátil; está no .gitignore.
OUTPUT_DIR = os.path.join(BASE_DIR, "_output")

# Limite de upload do .sql (2 MB é folgado para DDL).
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

# Dialetos suportados no select "Banco de origem" (valor -> rótulo).
SUPPORTED_DIALECTS = {
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "tsql": "SQL Server",
    "oracle": "Oracle",
    "sqlite": "SQLite",
}

# Defaults do formulário.
DEFAULT_SYSTEM_NAME = "SISTEMA"
DEFAULT_BASE_PACKAGE = "com.exemplo.app"
DEFAULT_DIALECT = "postgres"
