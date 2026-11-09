"""Configuração do servidor: um arquivo INI fora do código, com o endereço e a senha do banco e a chave de sessão.

O arquivo é o indicado em LEPTONS_CONFIG ou, sem a variável, /etc/leptons/leptons.conf. Modelo comentado:
deploy/leptons.conf.example. Caminhos relativos (data_dir) valem a partir da pasta do próprio arquivo.
"""
import configparser
import os
from pathlib import Path

ARQUIVO_PADRAO = "/etc/leptons/leptons.conf"


def _ler():
    caminho = Path(os.environ.get("LEPTONS_CONFIG") or ARQUIVO_PADRAO).expanduser().resolve()
    if not caminho.is_file():
        raise RuntimeError(f"Configuration file not found: {caminho}. Create it from deploy/leptons.conf.example "
                           "(or point the LEPTONS_CONFIG environment variable to it).")
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(caminho, encoding="utf-8")
    return caminho, cp


ARQUIVO, _cp = _ler()

BANCO = {
    "host": _cp.get("database", "host", fallback="localhost"),
    "port": _cp.getint("database", "port", fallback=3306),
    "database": _cp.get("database", "name", fallback="leptons"),
    "user": _cp.get("database", "user", fallback="leptons"),
    "password": _cp.get("database", "password", fallback=""),
}

# assina o cookie de sessão: fixa (trocar = desconectar todos); gerar com  python3 -c "import secrets; print(secrets.token_hex(32))"
CHAVE_SESSAO = _cp.get("app", "secret_key", fallback="").strip()
if len(CHAVE_SESSAO) < 32:
    raise RuntimeError(f"{ARQUIVO}: [app] secret_key is missing or shorter than 32 characters.")

# PDFs, anexos e arquivos de controle dos lotes enviados pelo navegador
PASTA_DADOS = (ARQUIVO.parent / _cp.get("app", "data_dir", fallback="/var/lib/leptons")).resolve()

# endereço usado nos links dos QR codes (ex.: https://leptons.lab.br); vazio = o endereço pelo qual a página foi aberta
URL_PUBLICA = _cp.get("app", "public_url", fallback="").strip().rstrip("/")

# cookie de sessão só por HTTPS (desligar apenas para testar sem HTTPS, ex.: no computador de desenvolvimento)
COOKIES_SEGUROS = _cp.getboolean("app", "secure_cookies", fallback=True)
