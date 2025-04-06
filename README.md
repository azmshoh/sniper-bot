# Trading Bot

Ushbu loyiha kripto-valyuta bozorida savdo operatsiyalarini avtomatlashtirish uchun yaratilgan trading bot hisoblanadi. Bot yangi tokenlarni kuzatish, xavfsizlik tahlili, likvidlik tahlili va savdo strategiyalarini amalga oshirish imkonini beradi.

## Loyiha tuzilishi

### Asosiy fayllar

- **bot.py** - Asosiy bot dasturi, yangi tokenlarni kuzatish va savdo operatsiyalarini boshqarish logikasi
- **migration.py** - Ma'lumotlar bazasi migratsiya skripti, jadvallarni yaratish va yangilash uchun

### Konfiguratsiya

- **config/settings.py** - Barcha sozlamalar, tarmoq parametrlari, valyuta juftliklari, RPC URLlar, savdo strategiyalari va xavfsizlik parametrlari

### Kontraktlar

- **contracts/abis.py** - Ethereum/BSC/Polygon smart kontraktlari uchun ABI (Application Binary Interface) ta'riflari
- **contracts/contract_manager.py** - Smart kontraktlar bilan ishlash uchun menejer, token tahlili, likvidlik tekshiruvi va narx hisoblash funksiyalari

### Ma'lumotlar bazasi

- **database/db_manager.py** - SQLite ma'lumotlar bazasi bilan ishlash uchun menejer, tokenlarni saqlash, savdo operatsiyalarini kuzatish va RPC URLlarini boshqarish

### Trading

- **trading/trader.py** - Trading operatsiyalari uchun klass, tokenlarni sotib olish va sotish, take-profit va stop-loss strategiyalari

### Foydali utilitalar

- **utils/logger.py** - Logging konfiguratsiyasi va xatolarni qayd qilish funksiyalari
- **utils/rpc_manager.py** - RPC (Remote Procedure Call) bilan ishlash uchun menejer, RPC almashtirib ishlash va urinishlarni takrorlash logikasi

## Asosiy funksionallik

1. **Yangi tokenlarni kuzatish**: Bot doimiy ravishda yangi yaratilgan token juftliklarini (pairs) kuzatib boradi
2. **Likvidlik analizi**: Yangi tokenlar uchun likvidlik miqdori va uning barqarorligini tekshiradi
3. **Token xavfsizligi**: Honeypot tokenlarni aniqlash, likvidlik qulflarini tekshirish
4. **Savdo strategiyalari**: 
   - Likvidlik qulflangan tokenlar uchun (balansdagi foiz miqdorida savdo)
   - Likvidlik qulflanmagan tokenlar uchun (minimal miqdorda savdo)
5. **Take-profit va Stop-loss**: Avtomat profitni olish va zararni cheklash
6. **RPC menejment**: RPC URLlar bilan bog'liq muammolarni avtomatik hal qilish

## O'rnatish va ishlatish

1. Talablarni o'rnatish:
```
pip install -r requirements.txt
```

2. `.env` faylini sozlash:
```
PRIVATE_KEY=your_private_key_here
ACTIVE_NETWORKS=bsc,ethereum
MIN_LIQUIDITY_BNB=50.0
MIN_LIQUIDITY_ETH=10.0
MIN_LIQUIDITY_MATIC=1000.0
MIN_BUY_AMOUNT_USD=1
BALANCE_PERCENT=10
MIN_LOCKED_PERCENT=50
MAX_BUY_TAX=10
MAX_SELL_TAX=10
INITIAL_PRICE_MONITOR=300
```

3. Botni ishga tushirish:
```
python bot.py
```

## Loyiha modullari

### NetworkMonitor

Bu klass bitta tarmoq va DEX uchun yangi tokenlarni kuzatadi:
- Yangi token juftliklari yaratilishini kuzatish
- Likvidlik tahlili
- Token xavfsizligi tekshiruvi
- Savdo operatsiyalarini boshqarish

### TokenMonitor

Asosiy kuzatish klassi, barcha tarmoq monitorlarini boshqaradi:
- Tarmoq monitorlarini yaratish
- Eskirgan savdolarni yopish
- Ma'lumotlar bazasi bilan ishlash

### TokenTrader

Savdo operatsiyalarini amalga oshirish uchun klass:
- Tokenlarni sotib olish va sotish
- Savdo miqdorini hisoblash
- Take-profit darajalarini aniqlash

### ContractManager

Smart kontraktlar bilan ishlash uchun klass:
- Factory, Router va Token kontraktlarini boshqarish
- Token narxlarini olish
- Likvidlik tahlili va qulflarini tekshirish

### RPCManager

RPC ulanishlarini boshqarish uchun klass:
- RPC URLlar almashtirib ishlash
- Ulanish xatoliklarini qayta takrorlash
- Ma'lumotlar bazasida ishonchli RPC URLlarni saqlash

### DatabaseManager

Ma'lumotlar bazasi bilan ishlash uchun klass:
- Yangi tokenlarni saqlash
- Savdo operatsiyalarini kuzatish
- RPC URLlarini boshqarish

## Savdo strategiyalari

1. **Likvidlik qulflangan tokenlar**: Hamyon balansining 10% qismida savdo qilish va profitni 3X, 10X va 50X darajalarda olish
2. **Likvidlik qulflanmagan tokenlar**: $1 miqdorda savdo qilish va profitni 2X, 5X, 10X va 20X darajalarda olish
3. **Stop-loss**: 20% zararni cheklab savdoni to'xtatish
4. **Trailing stop**: Token narxi maksimal darajadan 20% tushganda qolgan tokenlarni sotish

## Xavfsizlik tekshiruvlari

1. **Honeypot testi**: Token sotilishi mumkinligini tekshirish
2. **Likvidlik tekshiruvi**: Minimal likvidlik talablariga javob berishini tekshirish
3. **Likvidlik qulfi**: Likvidlikning qulflanganligini turli platformalarda tekshirish
4. **Narx monitoringi**: 5 daqiqa ichida 2X ga yetmaydigan tokenlarni avtomat sotib chiqish

## Tarmoqlar

- **BSC (Binance Smart Chain)**: PancakeSwap, Biswap
- **Ethereum**: Uniswap V2
- **Polygon**: QuickSwap