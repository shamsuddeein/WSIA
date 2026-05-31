#!/bin/bash
set -e

REMOTE_USER="shamo"
REMOTE_HOST="155.133.23.25"
REMOTE_DIR="~/projects/wsia"

echo "=========================================================="
echo "🚀 Starting WSIA Production Deployment to $REMOTE_HOST"
echo "=========================================================="

echo "📦 Transferring files via rsync..."
rsync -avz --exclude 'venv' --exclude '.git' --exclude '__pycache__' --exclude 'db.sqlite3' ./ $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/

echo "🔧 Connecting to server to build and launch the stack..."
ssh $REMOTE_USER@$REMOTE_HOST << 'EOF'
    set -e
    
    cd ~/projects/wsia

    echo "⚙️  Configuring environment variables..."
    if grep -q "^ALLOWED_HOSTS=" .env; then
        sed -i 's/^ALLOWED_HOSTS=.*/ALLOWED_HOSTS=155.133.23.25,localhost,127.0.0.1/' .env
    else
        echo "ALLOWED_HOSTS=155.133.23.25,localhost,127.0.0.1" >> .env
    fi

    echo "🐳 Building and starting Docker containers..."
    docker compose down || true
    docker compose up --build -d
    
    echo "🛠️  Running database migrations..."
    docker compose exec -T web python manage.py migrate

    echo "✅ Deployment complete! API Docs are live at http://155.133.23.25:8001/api/docs/"
EOF