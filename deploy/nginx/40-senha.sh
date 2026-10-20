#!/bin/sh
# Gera o arquivo de senha do nginx (HTTP Basic) a partir de SIGADASH_USUARIO / SIGADASH_SENHA.
set -eu

if [ -z "${SIGADASH_SENHA:-}" ]; then
    echo "ERRO: defina SIGADASH_SENHA no arquivo .env" >&2
    exit 1
fi

mkdir -p /etc/nginx/senhas
# mkpasswd (busybox) já vem na imagem; o nginx aceita hashes SHA-512 ($6$...) com sal aleatório.
hash=$(printf '%s' "$SIGADASH_SENHA" | mkpasswd -m sha512)
printf '%s:%s\n' "${SIGADASH_USUARIO:-sigadash}" "$hash" > /etc/nginx/senhas/.htpasswd
chmod 640 /etc/nginx/senhas/.htpasswd
chown root:nginx /etc/nginx/senhas/.htpasswd
