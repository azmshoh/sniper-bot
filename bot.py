import asyncio
import logging
from datetime import datetime
import time
from web3 import Web3
from typing import Dict, List
import os
from config.settings import (
    NETWORKS,
    POLLING_INTERVAL,
    PRICE_CHECK_INTERVAL,
    PRICE_TARGETS,
    LOG_FILE,
    LOG_FORMAT,
    ACTIVE_NETWORKS,
    TRADING
)
from migration import run_migrations
from utils.rpc_manager import RPCManager
from utils.logger import setup_logger
from database.db_manager import DatabaseManager
from contracts.contract_manager import ContractManager
from trading.trader import TokenTrader
from dotenv import load_dotenv
# Load environment variables
load_dotenv()
class NetworkMonitor:
    """Monitor for a specific network and DEX"""
    def __init__(self, network: str, dex: str, trader: TokenTrader = None):
        try:
            # Basic setup
            self.network = network
            self.dex = dex
            
            # Get network and DEX config
            self.network_config = NETWORKS[network]
            self.dex_config = self.network_config['dexes'][dex]
            
            # Initialize database and RPC manager
            self.db_manager = DatabaseManager()
            self.rpc_manager = RPCManager(network, self.db_manager)
            self.contract_manager = ContractManager(self.rpc_manager.web3, network, dex)
            
            self._price_cache = {}  # Narxlarni keshlash uchun
            self._cache_timeout = 30  # 30 sekund
            # Set trader if provided
            self.trader = trader
            
            # Initialize monitoring variables
            self.latest_block = 0
            self.next_price_check = 0
            self.trade_fails = {}
            
            logging.info(f"Monitor initialized for {network}/{dex}")
            
        except Exception as e:
            logging.error(f"Error initializing monitor for {network}/{dex}: {e}")
            raise

 
    async def get_cached_price(self, token_address: str):
        """Keshdan narxni olish yoki yangilash"""
        now = time.time()
        if token_address in self._price_cache:
            cached_price, timestamp = self._price_cache[token_address]
            if now - timestamp < self._cache_timeout:
                return cached_price
                
        price = await self.contract_manager.get_token_price(
            self.rpc_manager,
            token_address
        )
        self._price_cache[token_address] = (price, now)
        return price
    async def monitor_token_events(self, token_address: str, db_manager: DatabaseManager):
        """Token likvidligini kuzatish"""
        try:
            logging.info(f"Starting liquidity monitoring for {token_address}")
            
            # Juftlik manzilini olish
            pair_address = await self.rpc_manager.execute_with_retry(
                lambda: self.contract_manager.factory_contract.functions.getPair(
                    token_address,
                    self.contract_manager.wtoken_address
                ).call()
            )
            
            if pair_address == "0x0000000000000000000000000000000000000000":
                logging.info(f"No pair found for {token_address}")
                return
            
            logging.info(f"Found pair address: {pair_address}")
            pair_contract = self.contract_manager.get_pair_contract(pair_address)
            
            # Likvidlikni kuzatish
            monitoring_time = 30  # yarim daqiqa
            start_time = time.time()
            last_check = 0
            check_interval = 1
            
            stable_liquidity_count = 0  # Barqaror likvidlik soni
            required_stable_checks = 3   # Kerakli barqaror tekshiruvlar soni
            last_liquidity = 0
            
            logging.info(f"Likvidlikni 30soniya tekshirish {token_address}")
            
            while time.time() - start_time < monitoring_time:
                current_time = time.time()
                if current_time - last_check >= check_interval:
                    try:
                        # Likvidlikni olish
                        reserves = await self.rpc_manager.execute_with_retry(
                            lambda: pair_contract.functions.getReserves().call()
                        )
                        
                        token0 = await self.rpc_manager.execute_with_retry(
                            lambda: pair_contract.functions.token0().call()
                        )
                        
                        if token0.lower() == token_address.lower():
                            token_reserve, bnb_reserve = reserves[0], reserves[1]
                        else:
                            token_reserve, bnb_reserve = reserves[1], reserves[0]
                            
                        bnb_liquidity = self.rpc_manager.web3.from_wei(bnb_reserve, 'ether')
                        direct_balance = await self.rpc_manager.execute_with_retry(
                            lambda: self.rpc_manager.web3.eth.get_balance(pair_address)
                        )
                        direct_bnb = self.rpc_manager.web3.from_wei(direct_balance, 'ether')
                        
                        actual_liquidity = max(bnb_liquidity, direct_bnb)
                        
                        # Likvidlik barqarorligini tekshirish
                        if abs(actual_liquidity - last_liquidity) < 0.1:  # 0.1 BNB farq chegarasi
                            stable_liquidity_count += 1
                        else:
                            stable_liquidity_count = 0
                        
                        last_liquidity = actual_liquidity
                        
                        logging.info(
                            f"Liquidity check for {token_address}:\n"
                            f"Reserve BNB: {bnb_liquidity:.4f}\n"
                            f"Direct BNB: {direct_bnb:.4f}\n"
                            f"Actual liquidity: {actual_liquidity:.4f} BNB"
                        )
                        
                        # Likvidlik yetarli va barqaror bo'lsa
                        if actual_liquidity >= self.contract_manager.min_liquidity and stable_liquidity_count >= required_stable_checks:
                            token_contract = self.contract_manager.get_token_contract(token_address)
                            token_decimals = await self.rpc_manager.execute_with_retry(
                                lambda: token_contract.functions.decimals().call()
                            )
                            token_amount = token_reserve / (10 ** token_decimals)
                            
                            logging.info(
                                f"🎯 Sufficient liquidity found!\n"
                                f"Token: {token_address}\n"
                                f"BNB Liquidity: {actual_liquidity:.4f} BNB\n"
                                f"Token Amount: {token_amount:.2f} tokens\n"
                                f"Required: {self.contract_manager.min_liquidity} BNB"
                            )
                            # Savdo operatsiyasini bajarish
                            await self.process_liquidity_event(token_address, pair_address, db_manager, actual_liquidity)
                            return
                                
                        last_check = current_time
                            
                    except Exception as e:
                        logging.error(f"Error checking liquidity for {token_address}: {e}")
                        continue
                        
                await asyncio.sleep(1)
                    
            logging.info(f"Monitoring period ended for {token_address} without finding stable liquidity")
                    
        except Exception as e:
            logging.error(f"Error monitoring liquidity for {token_address}: {e}")

    async def process_liquidity_event(self, token_address: str, pair_address: str, db_manager: DatabaseManager, confirmed_liquidity: float):
        """Process token trading"""
        try:
            if not TRADING['enabled'] or not self.trader:
                return
                
            # Token security analysis
            analysis = await self.contract_manager.analyze_token(
                self.rpc_manager,
                token_address,
                confirmed_liquidity
            )
            
            if not analysis['success']:
                logging.warning(f"⚠️ Token analysis failed: {analysis['message']}")
                return
                
            details = analysis['details']
            token_info = details['token_info']
            
            logging.info(
                f"Token analysis:\n"
                f"Name: {token_info['name']} ({token_info['symbol']})\n"
                f"Liquidity: {details['native_liquidity']:.4f} {details['native_currency']}\n" 
                f"Is Locked: {'Yes' if details['is_locked'] else 'No'}\n"
                f"Price: {details['initial_price']:.12f} {details['native_currency']}"
            )
            
            # Check sufficient liquidity
            if not details['has_liquidity'] or details['native_liquidity'] < TRADING['min_liquidity_bnb']:
                logging.warning(
                    f"⚠️ Insufficient liquidity:\n"
                    f"Current: {details['native_liquidity']:.4f} {details['native_currency']}\n"
                    f"Required: {TRADING['min_liquidity_bnb']} {details['native_currency']}"
                )
                return
            
            # Calculate buy amount using initial price
            if details['is_locked']:
                # Locked liquidity - use percentage from balance
                amount_native, _ = await self.trader.calculate_buy_amount(self.rpc_manager.web3, True)
                logging.info(
                    f"🔒 Liquidity locked. Trading {self.trader.balance_percent}% of balance: "
                    f"{amount_native:.4f} {details['native_currency']}"
                )
            else:
                # Unlocked liquidity - convert USD amount to native currency
                amount_native = self.trader.min_buy_amount_usd / details['initial_price']
                logging.info(
                    f"🔓 Liquidity unlocked. Trading ${self.trader.min_buy_amount_usd} equivalent: "
                    f"{amount_native:.4f} {details['native_currency']}"
                )
            
            # Token xavfsizligi va sotish imkoniyatini tekshirish
            can_sell = await self.check_can_sell(
                token_address,
                self.contract_manager.router_contract,
                details['initial_price']
            )

            if not can_sell:
                logging.warning(
                    f"⚠️ Token sotilishi mumkin emas (Honeypot):\n"
                    f"Token: {token_address}\n"
                    f"Name: {token_info['name']}"
                )
                return
            # Execute buy
            buy_result = await self.trader.buy_token(
                self.rpc_manager.web3,
                token_address,
                self.contract_manager.router_contract,
                details['is_locked'],
                amount_native
            )
            
            if not buy_result['success']:
                logging.error(f"❌ Sotib olish amalga oshmadi: {buy_result['message']}")
                return
                
            logging.info(
                f"✅ Token sotib olindi!\n"
                f"Token: {token_info['name']}\n"
                f"Amount: {buy_result['amount_in']} {details['native_currency']}\n"
                f"TX Hash: {buy_result['tx_hash']}"
            )
            
            # Bazaga saqlash
            db_manager.save_trade(
                token_address,
                self.network,
                self.dex,
                'buy',
                buy_result['amount_in'],
                buy_result['token_amount'],
                details['initial_price'],
                buy_result['tx_hash']
            )

            # Savdo monitoringini boshlash
            asyncio.create_task(
                self.monitor_trade(
                    token_address,
                    details['initial_price'],
                    db_manager
                )
            )
                    
        except Exception as e:
            logging.error(f"Error processing liquidity event for {token_address}: {e}")

    # monitor_trade metodida
    async def monitor_trade(self, token_address: str, entry_price: float, db_manager: DatabaseManager):
        """Savdoni monitoring qilish"""
        try:
            initial_monitoring = True
            last_price_check = 0
            price_check_interval = 2  # Har 2 sekundda narxni tekshirish
            
            while True:
                current_time = time.time()
                
                if current_time - last_price_check >= price_check_interval:
                    try:
                        # Joriy narx
                        current_price = await self.contract_manager.get_token_price(
                            self.rpc_manager,
                            token_address
                        )
                        
                        if not current_price:
                            await asyncio.sleep(5)
                            continue
                        
                        # Decimal va float muammosini hal qilish
                        current_price = float(current_price)
                        entry_price = float(entry_price)
                        
                        price_change = current_price / entry_price
                        
                        # Dastlabki 5 daqiqa monitoringi
                        if initial_monitoring:
                            if current_time - last_price_check >= 300:  # 5 daqiqa
                                initial_monitoring = False
                                if price_change < 2:  # 2x ga yetmagan
                                    logging.info(
                                        f"⚠️ 5 daqiqa ichida 2x ga yetmadi.\n"
                                        f"Token: {token_address}\n"
                                        f"Entry: {entry_price:.12f}\n"
                                        f"Current: {current_price:.12f}\n"
                                        f"Change: {price_change:.2f}x"
                                    )
                                    # Stop-loss ga o'tkazish
                                    await self.activate_stop_loss(
                                        token_address,
                                        db_manager,
                                        current_price,
                                        'no_2x_in_5min'
                                    )
                        
                        # Savdo strategiyasi
                        trades = db_manager.get_active_trades(self.network, self.dex)
                        for trade in trades:
                            if trade['token_address'] != token_address:
                                continue
                            
                            # Stop-loss (-20%)
                            if price_change <= TRADING['auto_sell']['stop_loss']:
                                await self.execute_sell(
                                    token_address,
                                    db_manager,
                                    'stop_loss',
                                    trade['remaining_amount']
                                )
                                return
                            
                            # Take-profit
                            for tp in TRADING['auto_sell']['take_profit']:
                                tp_key = f"tp_{tp['multiplier']}x"
                                
                                if price_change >= tp['multiplier'] and not trade.get(tp_key):
                                    amount_to_sell = int(trade['remaining_amount'] * (tp['percent'] / 100))
                                    
                                    if amount_to_sell > 0:
                                        sell_result = await self.execute_sell(
                                            token_address,
                                            db_manager,
                                            f'take_profit_{tp["multiplier"]}x',
                                            amount_to_sell
                                        )
                                        
                                        if sell_result and sell_result['success']:
                                            db_manager.update_trade_tp(token_address, tp_key)
                            
                            # Trailing stop
                            if TRADING['auto_sell']['trailing_stop']['enabled']:
                                trail_percent = TRADING['auto_sell']['trailing_stop']['percent'] / 100
                                
                                if not trade['highest_price'] or current_price > trade['highest_price']:
                                    db_manager.update_trade_high(token_address, current_price)
                                else:
                                    price_drop = (trade['highest_price'] - current_price) / trade['highest_price']
                                    if price_drop >= trail_percent:
                                        await self.execute_sell(
                                            token_address,
                                            db_manager,
                                            'trailing_stop',
                                            trade['remaining_amount']
                                        )
                                        return
                    
                    except Exception as e:
                        logging.error(f"Error in trade monitoring for {token_address}: {e}")
                    
                    last_price_check = current_time
                
                await asyncio.sleep(1)
        
        except Exception as e:
            logging.error(f"Error monitoring trade for {token_address}: {e}")
    async def activate_stop_loss(self, token_address: str, db_manager: DatabaseManager, 
                            current_price: float, reason: str):
            """Stop-loss ni faollashtirish"""
            try:
                trades = db_manager.get_active_trades(self.network, self.dex)
                for trade in trades:
                    if trade['token_address'] == token_address:
                        await self.execute_sell(
                            token_address,
                            db_manager,
                            reason,
                            trade['remaining_amount']
                        )
                        break
            except Exception as e:
                logging.error(f"Error activating stop-loss for {token_address}: {e}")
    
    async def process_new_token(self, token_address: str, db_manager: DatabaseManager):
        """Process new token and monitor its events"""
        try:
            logging.info(f"💡 New token found on {self.network}/{self.dex}: {token_address}")
            
            # Start monitoring token events
            asyncio.create_task(self.monitor_token_events(token_address, db_manager))
            
            # Initial token analysis
            analysis = await self.contract_manager.analyze_token(
                self.rpc_manager,
                token_address
            )
            
            if not analysis['success']:
                logging.warning(f"❌ Token skipped on {self.network}/{self.dex}: {analysis['message']}")
                return

            details = analysis['details']
            token_info = details['token_info']
            
            # Log analysis results
            logging.info(
                f"✅ New token analyzed: {token_address}\n"
                f"Network: {self.network}\n"
                f"DEX: {self.dex}\n"
                f"Name: {token_info['name']} ({token_info['symbol']})\n"
                f"Total Supply: {token_info['total_supply']:,.2f}\n"
                f"{details['native_currency']} Liquidity: {details['native_liquidity']:.4f}\n"
                f"Token Liquidity: {details['token_liquidity']:.4f}\n"
                f"Liquidity Locked: {'Yes' if details['is_locked'] else 'No'}\n"
                f"Lock Details: {details['lock_details']}\n"
                f"Initial Price: {details['initial_price']:.12f} {details['native_currency']}"
            )

            if TRADING['enabled'] and self.trader and self.network in TRADING['networks']:
                if (details['has_liquidity'] and details['is_locked'] and 
                    details['native_liquidity'] >= TRADING['min_liquidity_bnb']):
                    
                    # Parallel tekshiruvlar
                    analysis_tasks = await asyncio.gather(
                        self.trader.analyze_token(
                            self.rpc_manager.web3,
                            token_address,
                            self.contract_manager.router_contract,
                            self.contract_manager.get_token_contract(token_address)
                        ),
                        self.check_can_sell(
                            token_address,
                            self.contract_manager.router_contract,
                            details['initial_price']
                        )
                    )
                    
                    trade_analysis = analysis_tasks[0]
                    can_sell = analysis_tasks[1]

                    if not can_sell:
                        logging.warning(f"⚠️ Token sotilishi mumkin emas...")
                        return

                    if trade_analysis['success']:
                        # Execute buy order
                        buy_result = await self.trader.buy_token(
                            self.rpc_manager.web3,
                            token_address,
                            self.contract_manager.router_contract,
                            details['is_locked']  # Pass if liquidity is locked
                        )
                        
                        if buy_result['success']:
                            logging.info(
                                f"🎯 Token bought successfully!\n"
                                f"Token: {token_info['name']}\n"
                                f"Amount: {buy_result['amount_in']} {details['native_currency']}\n"
                                f"TX Hash: {buy_result['tx_hash']}"
                            )
                            # Save trading info to database
                            db_manager.save_trade(
                                token_address,
                                self.network,
                                self.dex,
                                'buy',
                                buy_result['amount_in'],
                                buy_result['token_amount'],
                                details['initial_price']
                            )
                        else:
                            logging.error(f"❌ Buy failed: {buy_result['message']}")
                    else:
                        logging.warning(f"⚠️ Token failed trading checks: {trade_analysis['message']}")
            
            # Save token to database for monitoring
            if details['has_liquidity'] and details['is_locked']:
                db_manager.save_token(
                    token_address,
                    self.network,
                    self.dex,
                    details['initial_price']
                )
                # Save lock information
                for platform, amount in details['lock_details'].items():
                    db_manager.save_lock(
                        token_address,
                        self.network,
                        platform,
                        amount
                    )
                logging.info(f"💾 Token saved for monitoring on {self.network}/{self.dex}!")
                    
        except Exception as e:
            logging.error(f"Error processing new token {token_address} on {self.network}/{self.dex}: {e}")
    async def check_can_sell(self, token_address: str, router_contract, price: float) -> bool:
        """Tokenni sotish mumkinligini tekshirish"""
        try:
            # Minimal miqdorda sotib olish (test uchun)
            test_amount_bnb = 0.0005
            
            # Tekshiruvdan oldin buy_result bo'lishi kerak
            buy_result = await self.trader.buy_token(
                self.rpc_manager.web3,
                token_address,
                router_contract,
                False,  # Likvidlik ochiq
                test_amount_bnb
            )
            
            # Agar sotib olish muvaffaqiyatsiz bo'lsa
            if not buy_result['success']:
                logging.warning(f"❌ Test xaridi amalga oshmadi: {buy_result.get('message', 'Nomalum xato')}")
                return False
            
            # Sotish tekshiruvi
            sell_result = await self.trader.sell_token(
                self.rpc_manager.web3,
                token_address,
                router_contract,
                int(buy_result.get('token_amount', 0) * 1.0),  # Sotib olingan tokenlarni sotish
                test_mode=True  # Test rejimi
            )
            
            if not sell_result['success']:
                logging.warning(f"❌ Test sotishi amalga oshmadi: {sell_result.get('message', 'Nomalum xato')}")
                return False
            
            logging.info(f"✅ Token sotilishi mumkin...")
            return True
                
        except Exception as e:
            logging.error(f"Error checking if token can be sold: {e}")
            return False
    async def monitor_initial_price(self, token_address: str, entry_price: float, db_manager: DatabaseManager):
        """5 daqiqa ichida 2x kutish"""
        try:
            monitor_time = int(os.getenv('INITIAL_PRICE_MONITOR', '300'))  # 5 daqiqa
            start_time = time.time()
            
            # entry_price ni float ga o'tkazamiz
            entry_price = float(entry_price)
            
            logging.info(
                f"🕒 5 daqiqalik narx monitoring boshlandi:\n"
                f"Token: {token_address}\n"
                f"Entry price: {entry_price:.12f}"
            )
            
            while time.time() - start_time < monitor_time:
                try:
                    current_price = await self.contract_manager.get_token_price(
                        self.rpc_manager,
                        token_address
                    )
                    
                    if not current_price:
                        await asyncio.sleep(5)
                        continue
                    
                    # current_price ni float ga o'tkazamiz
                    current_price = float(current_price)
                    price_change = current_price / entry_price
                    
                    if price_change >= 2:
                        logging.info(
                            f"🎯 5 daqiqa ichida 2x ga yetdi!\n"
                            f"Token: {token_address}\n"
                            f"Entry: {entry_price:.12f}\n"
                            f"Current: {current_price:.12f}\n"
                            f"Change: {price_change:.2f}x"
                        )
                        return True
                        
                    await asyncio.sleep(5)
                    
                except Exception as e:
                    logging.error(f"Error checking price for {token_address}: {e}")
                    await asyncio.sleep(5)
                    
            # 5 daqiqa ichida 2x bo'lmadi
            logging.info(
                f"⚠️ 5 daqiqa ichida 2x ga yetmadi!\n"
                f"Token: {token_address}\n"
                f"Entry: {entry_price:.12f}\n"
                f"Selling all tokens..."
            )
            
            # Barcha tokenlarni sotish
            trades = db_manager.get_active_trades(self.network, self.dex)
            for trade in trades:
                if trade['token_address'] == token_address:
                    await self.execute_sell(
                        token_address,
                        db_manager,
                        'no_2x_in_5min',
                        trade['remaining_amount']
                    )
                    break
                    
            return False
            
        except Exception as e:
            logging.error(f"Error monitoring initial price for {token_address}: {e}")
            return False
    
    async def check_positions(self, db_manager: DatabaseManager):
        """Trading pozitsiyalarini tekshirish va boshqarish"""
        if not (TRADING['enabled'] and self.trader and self.network in TRADING['networks']):
            return
                
        try:
            active_trades = db_manager.get_active_trades(self.network, self.dex)
            
            for trade in active_trades:
                token_address = trade['token_address']
                
                # Token mavjudligini tekshirish
                token_exists = await self.contract_manager.check_token_exists(token_address)
                if not token_exists:
                    logging.warning(f"Token topilmadi, savdoni tugatish: {token_address}")
                    db_manager.close_trade(token_address, 'token_not_found')
                    if token_address in self.trade_fails:
                        del self.trade_fails[token_address]
                    continue
                    
                entry_price = float(trade['entry_price'])
                
                try:
                    current_price = await self.contract_manager.get_token_price(
                        self.rpc_manager,
                        token_address
                    )
                    
                    if not current_price:
                        # Agar 3 marta narxni ololmasa, savdoni tugatish
                        if token_address not in self.trade_fails:
                            self.trade_fails[token_address] = 1
                        else:
                            self.trade_fails[token_address] += 1
                            
                        if self.trade_fails[token_address] >= 3:
                            logging.warning(f"Token narxi 3 marta olinmadi, savdoni tugatish: {token_address}")
                            db_manager.close_trade(token_address, 'price_check_failed')
                            del self.trade_fails[token_address]
                            continue
                        else:
                            logging.warning(f"❌ {token_address} uchun narx olib bo'lmadi. Urinish: {self.trade_fails[token_address]}/3")
                            continue
                    
                    # Narx olindi - urinishlar sonini o'chirish
                    if token_address in self.trade_fails:
                        del self.trade_fails[token_address]
                    
                    current_price = float(current_price)
                    price_change = current_price / entry_price
                    
                    logging.info(
                        f"Token holati:\n"
                        f"Address: {token_address}\n"
                        f"Entry: {entry_price:.12f}\n"
                        f"Current: {current_price:.12f}\n"
                        f"Change: {price_change:.2f}x"
                    )
                    
                    # Stop loss tekshiruvi (-20%)
                    if price_change <= float(TRADING['auto_sell']['stop_loss']):
                        logging.info(
                            f"🔻 Stop loss ishga tushdi!\n"
                            f"Token: {token_address}\n"
                            f"Loss: {(1 - price_change) * 100:.1f}%"
                        )
                        await self.execute_sell(
                            token_address, 
                            db_manager, 
                            'stop_loss',
                            trade['remaining_amount']
                        )
                        continue
                    
                    # Take profit tekshiruvi (2x=50%, 3x=25%, 4x=25%)
                    for tp in TRADING['auto_sell']['take_profit']:
                        tp_key = f"tp_{tp['multiplier']}x"
                        
                        if price_change >= tp['multiplier'] and not trade.get(tp_key):
                            amount_to_sell = int(trade['remaining_amount'] * (tp['percent'] / 100))
                            
                            if amount_to_sell > 0:
                                logging.info(
                                    f"🎯 Take profit {tp['multiplier']}x ishga tushdi!\n"
                                    f"Token: {token_address}\n"
                                    f"Selling: {tp['percent']}%\n"
                                    f"Amount: {amount_to_sell}\n"
                                    f"Profit: {(price_change - 1) * 100:.1f}%"
                                )
                                
                                sell_result = await self.execute_sell(
                                    token_address,
                                    db_manager,
                                    f'take_profit_{tp["multiplier"]}x',
                                    amount_to_sell
                                )
                                
                                if sell_result and sell_result['success']:
                                    db_manager.update_trade_tp(token_address, tp_key)
                                break
                    
                    # Trailing stop tekshiruvi (10% pastga tushsa)
                    if TRADING['auto_sell']['trailing_stop']['enabled']:
                        trail_percent = TRADING['auto_sell']['trailing_stop']['percent'] / 100
                        
                        # Eng yuqori narxni yangilash
                        if not trade['highest_price'] or current_price > trade['highest_price']:
                            db_manager.update_trade_high(token_address, current_price)
                            continue
                            
                        # Trailing stop tekshiruvi
                        price_drop = (trade['highest_price'] - current_price) / trade['highest_price']
                        if price_drop >= trail_percent:
                            logging.info(
                                f"🔻 Trailing stop ishga tushdi!\n"
                                f"Token: {token_address}\n"
                                f"High: {trade['highest_price']:.12f}\n"
                                f"Current: {current_price:.12f}\n"
                                f"Drop: {price_drop * 100:.1f}%"
                            )
                            await self.execute_sell(
                                token_address,
                                db_manager,
                                'trailing_stop',
                                trade['remaining_amount']
                            )
                    
                except Exception as e:
                    logging.error(f"Error checking position for {token_address}: {e}")
                    continue
                    
        except Exception as e:
            logging.error(f"Error checking positions: {e}")

    async def execute_sell(self, token_address: str, db_manager: DatabaseManager, reason: str, amount: int) -> dict:
        """Tokenni sotish"""
        try:
            # Sotish operatsiyasini amalga oshirish
            sell_result = await self.trader.sell_token(
                self.rpc_manager.web3,
                token_address,
                self.contract_manager.router_contract,
                amount
            )
            
            if sell_result['success']:
                logging.info(
                    f"💰 Token muvaffaqiyatli sotildi!\n"
                    f"Token: {token_address}\n"
                    f"Amount: {sell_result['amount_sold']}\n"
                    f"Received: {sell_result['amount_out']} {NETWORKS[self.network]['currency']}\n"
                    f"Reason: {reason}\n"
                    f"TX Hash: {sell_result['tx_hash']}"
                )
                
                # Bazani yangilash
                db_manager.update_trade(
                    token_address,
                    'sell',
                    sell_result['amount_out'],
                    reason
                )
                
                return sell_result
            else:
                logging.error(f"❌ Sotish amalga oshmadi: {sell_result['message']}")
                return sell_result
                
        except Exception as e:
            logging.error(f"Error executing sell for {token_address}: {e}")
            return {
                'success': False,
                'message': str(e)
            }

    async def monitor_pairs(self, db_manager: DatabaseManager):
        """Monitor blockchain for new token pairs"""
        try:
            # RPC xatoliklari uchun qayta urinish mexanizmi
            max_retry_attempts = 2
            retry_count = 0

            while retry_count < max_retry_attempts:
                try:
                    # RPC menejerning Web3 instanceni qayta olish
                    self.rpc_manager.web3 = await self.rpc_manager.get_web3_for_network(self.network)

                    # Oxirgi block raqamini olish
                    if not self.latest_block:
                        self.latest_block = await self.rpc_manager.execute_with_retry(
                            lambda: self.rpc_manager.web3.eth.block_number
                        )
                        
                    pair_created_topic = self.contract_manager.get_pair_created_topic()
                    factory_address = NETWORKS[self.network]['dexes'][self.dex]['factory']
                    wrapped_token = NETWORKS[self.network]['dexes'][self.dex]['wtoken']

                    while True:
                        try:
                            # Joriy block raqamini olish
                            current_block = await self.rpc_manager.execute_with_retry(
                                lambda: self.rpc_manager.web3.eth.block_number
                            )
                            
                            # Block raqamlarini tekshirish
                            if current_block <= self.latest_block:
                                logging.warning(
                                    f"Block raqami noto'g'ri:\n"
                                    f"Latest: {self.latest_block}\n"
                                    f"Current: {current_block}\n"
                                    f"Keyingi urinishgacha kutilmoqda..."
                                )
                                await asyncio.sleep(POLLING_INTERVAL)
                                continue

                            # Loglarni olish
                            logs = await self.rpc_manager.execute_with_retry(
                                lambda: self.rpc_manager.web3.eth.get_logs({
                                    'fromBlock': self.latest_block,
                                    'toBlock': current_block,
                                    'address': factory_address,
                                    'topics': [pair_created_topic]
                                })
                            )

                            # Yangi juftliklarni tekshirish
                            for log in logs:
                                event = self.contract_manager.factory_contract.events.PairCreated().process_log(log)
                                token0, token1 = event['args']['token0'], event['args']['token1']
                                
                                # WETH/WBNB/WMATIC bo'lmagan tokenni topish
                                if token0.lower() == wrapped_token.lower():
                                    await self.process_new_token(token1, db_manager)
                                elif token1.lower() == wrapped_token.lower():
                                    await self.process_new_token(token0, db_manager)
                            
                            # Oxirgi block raqamini yangilash
                            self.latest_block = current_block
                            
                            # Aktiv pozitsiyalarni tekshirish
                            await self.check_positions(db_manager)
                                
                            # Xatoliklarni qayta tiklash
                            retry_count = 0
                                
                        except Exception as e:
                            if isinstance(e, KeyboardInterrupt):
                                raise
                            
                            # RPC URL bilan bog'liq xatoliklarni aniqlash
                            if "400 Client Error" in str(e) or "Connection refused" in str(e):
                                retry_count += 1
                                logging.warning(
                                    f"RPC xatosi ({retry_count}/{max_retry_attempts}): {e}\n"
                                    f"Keyingi urinishgacha kutilmoqda..."
                                )
                                
                                # RPC URLni bazadan o'chirish
                                self.rpc_manager.db_manager.update_rpc_status(
                                    self.network, 
                                    self.rpc_manager.current_rpc_url, 
                                    False, 
                                    datetime.now(), 
                                    str(e)
                                )
                                
                                # Kuting va qayta urinish
                                await asyncio.sleep(POLLING_INTERVAL * retry_count)
                                
                                # Agar maksimal urinishlar tugagan bo'lsa
                                if retry_count >= max_retry_attempts:
                                    logging.error(f"Maksimal urinishlar soni tugadi: {self.network}/{self.dex}")
                                    raise
                            else:
                                logging.error(f"Kutilmagan xatolik {self.network}/{self.dex}: {e}")
                                raise
                            
                        await asyncio.sleep(POLLING_INTERVAL)
                        
                except Exception as e:
                    logging.error(f"RPC ulanishda xatolik {self.network}/{self.dex}: {e}")
                    retry_count += 1
                    await asyncio.sleep(POLLING_INTERVAL * retry_count)
                    
                    # Agar maksimal urinishlar tugagan bo'lsa
                    if retry_count >= max_retry_attempts:
                        logging.critical(f"Barcha urinishlar amalga oshmadi: {self.network}/{self.dex}")
                        raise
            
        except KeyboardInterrupt:
            logging.info(f"Monitoring {self.network}/{self.dex} to'xtatildi")
        except Exception as e:
            logging.critical(f"Fatal xatolik {self.network}/{self.dex}: {e}")
            raise

class TokenMonitor:
    """Main monitoring class"""
    def __init__(self):
        try:
            # Setup logging
            setup_logger(LOG_FILE, LOG_FORMAT)

            # Run migrations
            run_migrations()
            
            # Initialize database
            self.db_manager = DatabaseManager()
            
            # Initialize trader if enabled
            self.trader = None
            if TRADING['enabled']:
                if not TRADING['private_key']:
                    raise ValueError("Private key not found in environment variables")
                logging.info("Initializing trader...")
                
                # Get network settings for first active network
                network = ACTIVE_NETWORKS[0]  # e.g. 'bsc'
                dex = list(NETWORKS[network]['dexes'].keys())[0]  # e.g. 'pancakeswap'
                
                network_config = NETWORKS[network]
                dex_config = network_config['dexes'][dex]
                
                network_settings = {
                    'wtoken': dex_config['wtoken'],
                    'currency': network_config['currency'],
                    'chain_id': network_config['id']
                }
                
                self.trader = TokenTrader(
                    private_key=TRADING['private_key'], 
                    network_settings=network_settings
                )
            
            # Initialize network monitors
            self.network_monitors: Dict[str, Dict[str, NetworkMonitor]] = {}
            self.setup_network_monitors()
            
        except Exception as e:
            logging.error(f"Error initializing TokenMonitor: {str(e)}")
            raise
        
    def setup_network_monitors(self):
        """Setup monitors for each active network and DEX"""
        for network in ACTIVE_NETWORKS:
            if network not in NETWORKS:
                continue
                
            self.network_monitors[network] = {}
            for dex in NETWORKS[network]['dexes'].keys():
                # Get network settings for this network/dex
                network_config = NETWORKS[network]
                dex_config = network_config['dexes'][dex]
                
                network_settings = {
                    'wtoken': dex_config['wtoken'],
                    'currency': network_config['currency'],
                    'chain_id': network_config['id']
                }
                
                # Create trader for this network if needed
                trader = None
                if self.trader and network in TRADING['networks']:
                    try:
                        trader = TokenTrader(
                            private_key=TRADING['private_key'],
                            network_settings=network_settings
                        )
                    except Exception as e:
                        logging.error(f"Error creating trader for {network}/{dex}: {e}")
                
                self.network_monitors[network][dex] = NetworkMonitor(
                    network=network,
                    dex=dex,
                    trader=trader
                )

    async def close_previous_trades(self):
        """Oldingi savdolarni yopish"""
        try:
            # Barcha faol savdolarni olish
            active_trades = self.db_manager.get_active_trades()
            
            logging.info(f"🔄 Boshlang'ich qayta ishga tushirishda {len(active_trades)} ta faol savdo topildi")
            
            # Barcha savdolarni yopish uchun tasklarni yaratish
            close_tasks = []
            for trade in active_trades:
                try:
                    # Har bir token uchun NetworkMonitor objectini topish
                    network = trade['network']
                    dex = trade['dex']
                    
                    if network in self.network_monitors and dex in self.network_monitors[network]:
                        monitor = self.network_monitors[network][dex]
                        
                        # Har bir sotish operatsiyasi uchun task yaratish
                        task = asyncio.create_task(
                            monitor.execute_sell(
                                trade['token_address'],
                                self.db_manager,
                                'initial_close',
                                int(float(trade['remaining_amount']))
                            )
                        )
                        close_tasks.append(task)
                    
                except Exception as e:
                    logging.error(f"Tokenni sotishga task yaratishda xatolik: {trade['token_address']} - {e}")
            
            # Barcha sotish tasklarini bajarish
            sell_results = await asyncio.gather(*close_tasks, return_exceptions=True)
            
            # Natijalarni logging qilish
            for trade, result in zip(active_trades, sell_results):
                if isinstance(result, Exception):
                    logging.error(f"Token sotishda xatolik: {trade['token_address']} - {result}")
                elif result.get('success'):
                    logging.info(
                        f"✅ Token sotildi: {trade['token_address']}\n"
                        f"Miqdor: {trade['remaining_amount']}\n"
                        f"Natija: {result.get('amount_out', 'Nomalum')} {trade['network'].upper()}"
                    )
                else:
                    logging.warning(
                        f"❌ Token sotishda muammo: {trade['token_address']}\n"
                        f"Sabab: {result.get('message', 'Nomalum xato')}"
                    )
        
        except Exception as e:
            logging.error(f"Oldingi savdolarni yopishda xatolik: {e}")

    async def run_monitors(self):
        """Run all network monitors concurrently"""
        try:
            # Oldingi savdolarni yopish
            await self.close_previous_trades()
            
            monitor_tasks = []
            
            for network, dex_monitors in self.network_monitors.items():
                for dex, monitor in dex_monitors.items():
                    task = asyncio.create_task(
                        monitor.monitor_pairs(self.db_manager)
                    )
                    monitor_tasks.append(task)
                    logging.info(f"Started monitor for {network}/{dex}")
            
            # Wait for all monitors
            await asyncio.gather(*monitor_tasks)
            
        except KeyboardInterrupt:
            logging.info("Shutting down all monitors gracefully...")
        except Exception as e:
            logging.error(f"Error running monitors: {e}")
        finally:
            self.db_manager.close()
async def main():
    monitor = TokenMonitor()
    await monitor.run_monitors()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Bot stopped due to error: {e}")