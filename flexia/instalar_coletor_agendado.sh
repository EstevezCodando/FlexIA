# Instala a coleta agendada da FlexIA na máquina do Code Editor (cron + Cavuca).
# A conta do workshop não permite Lambda com role própria (iam:PassRole bloqueado), então o
# agendamento roda aqui, com a role da própria instância. Colar no terminal do Code Editor.
bash <<'SCRIPT'
set -e
CONTA=$(aws sts get-caller-identity --query Account --output text)
BUCKET="ons-datalake-${CONTA}"
DIR="$HOME/flexia-coletor"
mkdir -p "$DIR/logs"

echo "== 1. código do coletor"
aws s3 cp "s3://${BUCKET}/deploy/coletor/" "$DIR/" --recursive --quiet
ls "$DIR"

echo "== 2. ambiente Python com Cavuca"
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install -q --upgrade pip
"$DIR/.venv/bin/pip" install -q "Cavuca[rag] @ git+https://github.com/EstevezCodando/Cavuca.git" pypdf boto3 duckdb pandas

echo "== 3. permissões da instância no bucket"
aws s3 ls "s3://${BUCKET}/docs/estado/" | head -3

echo "== 4. script de execução"
cat > "$DIR/rodar.sh" <<EOF
#!/bin/bash
# uso: rodar.sh diaria|semanal|mensal|previsao   (flock evita duas execuções simultâneas)
export FLEXIA_BUCKET=${BUCKET} AWS_REGION=us-east-1 PYTHONIOENCODING=utf-8
cd "$DIR"
if [ "\$1" = "previsao" ]; then
  exec "$DIR/.venv/bin/python" previsao_clima.py >> "$DIR/logs/previsao-\$(date +%Y%m%d).log" 2>&1
fi
exec flock -n "$DIR/.lock" bash -c '"$DIR/.venv/bin/python" coletor.py --frequencia "\$0" && "$DIR/.venv/bin/python" indexar.py' "\$1" \
  >> "$DIR/logs/\$1-\$(date +%Y%m%d).log" 2>&1
EOF
chmod +x "$DIR/rodar.sh"

echo "== 5. cron (horário de Brasília)"
if ! command -v crontab >/dev/null; then
  (sudo dnf install -y -q cronie || sudo apt-get install -y -qq cron) && (sudo systemctl enable --now crond 2>/dev/null || sudo systemctl enable --now cron)
fi
( crontab -l 2>/dev/null | grep -v flexia-coletor ; cat <<EOF
CRON_TZ=America/Sao_Paulo
30 5 * * * $DIR/rodar.sh previsao # flexia-coletor: previsão meteorológica 16 dias nos polos
0 6 * * *  $DIR/rodar.sh diaria   # flexia-coletor: notícias e manchetes
0 7 * * 1  $DIR/rodar.sh semanal  # flexia-coletor: leis, procedimentos, dados abertos
0 8 1 * *  $DIR/rodar.sh mensal   # flexia-coletor: publicações
EOF
) | crontab -
crontab -l | grep flexia

echo "== 6. teste: coleta diária agora (alguns minutos)"
"$DIR/rodar.sh" diaria; tail -5 "$DIR/logs/diaria-$(date +%Y%m%d).log"
SCRIPT
