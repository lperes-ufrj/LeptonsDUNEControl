# Instalação no servidor (Debian 13)

Duas máquinas virtuais, só com pacotes oficiais do Debian 13 (sem pip, sem fontes apt externas):

- **VM de banco**: MariaDB.
- **VM de aplicação**: nginx (HTTPS) → gunicorn → o programa (Flask, Python 3.13).

Portas: 443/tcp (e 80, que só redireciona) da rede do laboratório para a VM de aplicação; 3306/tcp só da VM de
aplicação para a VM de banco. O programa não acessa a Internet.

Nos comandos abaixo, troque `IP_APP` pelo IP da VM de aplicação e `IP_BANCO` pelo da VM de banco.

## 1. VM de banco

```bash
apt install mariadb-server mariadb-client
```

Aceitar conexões da rede: em `/etc/mysql/mariadb.conf.d/50-server.cnf`, `bind-address = IP_BANCO`; depois
`systemctl restart mariadb`.

Banco e usuário (`mariadb` como root):

```sql
CREATE DATABASE leptons CHARACTER SET utf8mb4;
CREATE USER 'leptons'@'IP_APP' IDENTIFIED BY 'uma-senha-forte';
GRANT ALL PRIVILEGES ON leptons.* TO 'leptons'@'IP_APP';
```

O programa cria as próprias tabelas ao iniciar.

## 2. VM de aplicação

```bash
apt install python3 python3-flask python3-pymysql python3-reportlab python3-pil \
    python3-qrcode python3-openpyxl fonts-dejavu-core gunicorn nginx mariadb-client git
```

Usuário do serviço, código e pastas:

```bash
adduser --system --group --home /var/lib/leptons leptons
install -d -o leptons -g leptons -m 750 /var/lib/leptons
git clone https://github.com/lperes-ufrj/LeptonsDUNEControl.git /opt/leptons
install -d -g leptons -m 750 /etc/leptons
install -g leptons -m 640 /opt/leptons/deploy/leptons.conf.example /etc/leptons/leptons.conf
```

Em `/etc/leptons/leptons.conf`: o endereço e a senha do banco, uma `secret_key` nova
(`python3 -c "import secrets; print(secrets.token_hex(32))"`) e o `public_url` (o endereço HTTPS do servidor, usado
nos links dos QR codes).

Conferir a configuração e a conexão com o banco (cria as tabelas):

```bash
cd /opt/leptons
sudo -u leptons env LEPTONS_CONFIG=/etc/leptons/leptons.conf flask --app "webapp.app:criar_app()" routes > /dev/null && echo OK
```

Serviço:

```bash
cp /opt/leptons/deploy/leptons.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now leptons
```

nginx (ajuste `server_name` e os caminhos do certificado no arquivo):

```bash
cp /opt/leptons/deploy/nginx-leptons.conf /etc/nginx/sites-available/leptons
ln -s /etc/nginx/sites-available/leptons /etc/nginx/sites-enabled/leptons
rm /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

## 3. Dados atuais (uma vez)

Com o programa antigo fechado em todos os computadores, copie `rastreabilidade.db`, `lotes.db` e `usuarios.db`
para a VM de aplicação e rode a migração:

```bash
install -d -o leptons -g leptons /var/tmp/leptons-sqlite
cp rastreabilidade.db lotes.db usuarios.db /var/tmp/leptons-sqlite/
chown leptons:leptons /var/tmp/leptons-sqlite/*
cd /opt/leptons
sudo -u leptons env LEPTONS_CONFIG=/etc/leptons/leptons.conf python3 deploy/migrar_sqlite.py /var/tmp/leptons-sqlite
```

A migração só roda com o banco vazio, grava tudo numa transação e mostra as contagens de cada tabela. Os usuários
continuam com as mesmas senhas. Depois de conferir no navegador, apague `/var/tmp/leptons-sqlite`.

Instalação nova, sem dados: crie a primeira conta Admin com

```bash
cd /opt/leptons
sudo -u leptons env LEPTONS_CONFIG=/etc/leptons/leptons.conf flask --app "webapp.app:criar_app()" create-admin
```

## 4. Atualizar o programa

```bash
cd /opt/leptons && git pull && systemctl restart leptons
```

## 5. Backup

- Banco: `mariadb-dump --single-transaction leptons > leptons_$(date +%F).sql`
- Arquivos enviados pelo navegador: `/var/lib/leptons` (`anexos/`, `arquivos_lotes/`; `relatorios_pdf/` é gerado de
  novo quando preciso)
- Configuração: `/etc/leptons/leptons.conf`

## Logs

`journalctl -u leptons` (erros e acessos do programa) e `/var/log/nginx/`.
