#!/bin/bash
# 🔑 НАСТРОЙКА PRODUCTION API КЛЮЧЕЙ
# Замените значения на ваши реальные production ключи

echo "🔑 Настройка Production API ключей..."

# OKX Production API ключи
read -p "Введите OKX API Key: " OKX_KEY
read -s -p "Введите OKX API Secret: " OKX_SECRET
echo
read -p "Введите OKX Passphrase: " OKX_PASSPHRASE

# Bitget Production API ключи  
read -p "Введите Bitget API Key: " BITGET_KEY
read -s -p "Введите Bitget API Secret: " BITGET_SECRET
echo
read -p "Введите Bitget Passphrase: " BITGET_PASSPHRASE

# Phemex Production API ключи
read -p "Введите Phemex API Key: " PHEMEX_KEY
read -s -p "Введите Phemex API Secret: " PHEMEX_SECRET
echo

# Экспорт переменных
export OKX_API_KEY="$OKX_KEY"
export OKX_API_SECRET="$OKX_SECRET" 
export OKX_PASSPHRASE="$OKX_PASSPHRASE"

export BITGET_API_KEY="$BITGET_KEY"
export BITGET_API_SECRET="$BITGET_SECRET"
export BITGET_PASSPHRASE="$BITGET_PASSPHRASE"

export PHEMEX_API_KEY="$PHEMEX_KEY"
export PHEMEX_API_SECRET="$PHEMEX_SECRET"

echo "✅ API ключи установлены!"

# Сохранение в ~/.bashrc для постоянного использования
echo "💾 Сохранение в ~/.bashrc..."
{
    echo ""
    echo "# Production Trading API Keys - $(date)"
    echo "export OKX_API_KEY=\"$OKX_KEY\""
    echo "export OKX_API_SECRET=\"$OKX_SECRET\""  
    echo "export OKX_PASSPHRASE=\"$OKX_PASSPHRASE\""
    echo ""
    echo "export BITGET_API_KEY=\"$BITGET_KEY\""
    echo "export BITGET_API_SECRET=\"$BITGET_SECRET\""
    echo "export BITGET_PASSPHRASE=\"$BITGET_PASSPHRASE\""
    echo ""
    echo "export PHEMEX_API_KEY=\"$PHEMEX_KEY\""
    echo "export PHEMEX_API_SECRET=\"$PHEMEX_SECRET\""
} >> ~/.bashrc

echo "✅ API ключи сохранены в ~/.bashrc"
echo ""
echo "🚀 Теперь запустите тест:"
echo "python3 test_real_trading_setup.py"
