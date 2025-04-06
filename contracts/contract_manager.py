import logging
import os
from web3 import Web3
from typing import Optional, Tuple, Dict
from config.settings import NETWORKS, LOCK_CONTRACTS, TRADING
from contracts.abis import FACTORY_ABI, ROUTER_ABI, TOKEN_ABI, LP_PAIR_ABI
from utils.rpc_manager import RPCManager

class ContractManager:
    def __init__(self, web3: Web3, network: str, dex: str):
        self.web3 = web3
        self.network = network
        self.dex = dex
        
        # Get network and DEX configs
        self.network_config = NETWORKS[network]
        self.dex_config = self.network_config['dexes'][dex]
        
        # Set minimum liquidity from network config
        self.min_liquidity = self.network_config['min_liquidity']
        self.native_currency = self.network_config['currency']
        
        self.setup_contracts()

    
    # contract_manager.py faylida
    async def check_token_exists(self, token_address: str) -> bool:
        """Tokenni mavjudligini tekshirish"""
        try:
            token_contract = self.get_token_contract(token_address)
            
            # Token kodini olishga harakat qilish
            code = self.web3.eth.get_code(token_address)
            
            # Agar kod bo'sh bo'lsa, token mavjud emas
            if code == '0x' or code == b'':
                logging.warning(f"Token kodi topilmadi: {token_address}")
                return False
                
            # Token nomini olishga harakat qilish
            try:
                name = token_contract.functions.name().call()
                return True
            except Exception as e:
                logging.warning(f"Token nomi olinmadi: {token_address}, {str(e)}")
                return False
                
        except Exception as e:
            logging.error(f"Error checking token existence: {token_address}, {str(e)}")
            return False
    def get_pair_contract(self, pair_address: str):
        """Get LP pair contract instance"""
        return self.web3.eth.contract(address=pair_address, abi=LP_PAIR_ABI)
    def setup_contracts(self):
        """Setup smart contracts for specific network and DEX"""
        try:
            self.factory_contract = self.web3.eth.contract(
                address=self.dex_config['factory'], 
                abi=FACTORY_ABI
            )
            self.router_contract = self.web3.eth.contract(
                address=self.dex_config['router'], 
                abi=ROUTER_ABI
            )
            self.wtoken_address = self.dex_config['wtoken']
            
            logging.info(f"Contracts setup successful for {self.network}/{self.dex}")
            logging.info(f"Minimum liquidity requirement: {self.min_liquidity} {self.network_config['currency']}")
            
        except Exception as e:
            logging.error(f"Contract setup error for {self.network}/{self.dex}: {str(e)}")
            raise

    def get_token_contract(self, token_address: str):
        """Get token contract instance"""
        return self.web3.eth.contract(address=token_address, abi=TOKEN_ABI)

    async def check_liquidity_details(self, rpc_manager, token_address: str) -> Tuple[bool, float, float]:
        """Check token liquidity details in last blocks"""
        try:
            # Get pair address
            pair_address = await rpc_manager.execute_with_retry(
                lambda: self.factory_contract.functions.getPair(
                    token_address, 
                    self.wtoken_address
                ).call()
            )
            
            if pair_address == "0x0000000000000000000000000000000000000000":
                logging.warning(f"No liquidity pair found for {token_address}")
                return False, 0, 0

            token_contract = self.get_token_contract(token_address)
            
            # Get current block
            current_block = await rpc_manager.execute_with_retry(
                lambda: rpc_manager.web3.eth.block_number
            )
            
            # Check last blocks for liquidity changes
            blocks_to_check = int(os.getenv('BLOCKS_TO_CHECK', '10'))
            min_liquidity = float('inf')
            liquidity_history = []
            
            for block in range(current_block - blocks_to_check, current_block + 1):
                try:
                    balance = await rpc_manager.execute_with_retry(
                        lambda: rpc_manager.web3.eth.get_balance(pair_address, block_identifier=block)
                    )
                    liquidity = rpc_manager.web3.from_wei(balance, 'ether')
                    min_liquidity = min(min_liquidity, liquidity)
                    liquidity_history.append(liquidity)
                except Exception as e:
                    logging.debug(f"Error checking block {block}: {e}")
                    continue
            
            if min_liquidity == float('inf') or not liquidity_history:
                logging.warning(f"Could not get liquidity history for {token_address}")
                return False, 0, 0
                
            # Get token amount
            token_balance = await rpc_manager.execute_with_retry(
                lambda: token_contract.functions.balanceOf(pair_address).call()
            )
            
            token_decimals = await rpc_manager.execute_with_retry(
                lambda: token_contract.functions.decimals().call()
            )
            
            token_liquidity = token_balance / (10 ** token_decimals)
            
            # Check minimum liquidity requirement
            has_min_liquidity = min_liquidity >= self.min_liquidity
            
            if has_min_liquidity:
                logging.info(
                    f"Liquidity check passed for {token_address}:\n"
                    f"Minimum liquidity found: {min_liquidity:.4f} {self.network_config['currency']}\n"
                    f"Required minimum: {self.min_liquidity} {self.network_config['currency']}\n"
                    f"Token liquidity: {token_liquidity:.2f} tokens\n"
                    f"Blocks checked: {len(liquidity_history)}"
                )
            else:
                logging.warning(
                    f"Insufficient liquidity for {token_address}:\n"
                    f"Minimum liquidity found: {min_liquidity:.4f} {self.network_config['currency']}\n"
                    f"Required minimum: {self.min_liquidity} {self.network_config['currency']}"
                )
            
            return has_min_liquidity, min_liquidity, token_liquidity
            
        except Exception as e:
            logging.error(f"Error checking liquidity for {token_address} on {self.network}/{self.dex}: {e}")
            return False, 0, 0

    async def check_token_locks(self, rpc_manager, token_address: str) -> Tuple[bool, Dict[str, float]]:
        """Check if token liquidity is locked on various platforms"""
        try:
            token_contract = self.get_token_contract(token_address)
            pair_address = await rpc_manager.execute_with_retry(
                lambda: self.factory_contract.functions.getPair(
                    token_address, 
                    self.wtoken_address
                ).call()
            )

            locks_found = {}
            network_locks = LOCK_CONTRACTS.get(self.network, {})
            total_locked = 0
            
            # Check each lock platform
            for platform, lock_address in network_locks.items():
                try:
                    lp_balance = await rpc_manager.execute_with_retry(
                        lambda: token_contract.functions.balanceOf(lock_address).call()
                    )
                    
                    if lp_balance > 0:
                        locked_amount = self.web3.from_wei(lp_balance, 'ether')
                        locks_found[platform] = locked_amount
                        total_locked += locked_amount
                except Exception as e:
                    logging.debug(f"Error checking {platform} lock: {e}")
                    continue

            # Get total supply
            total_supply = await rpc_manager.execute_with_retry(
                lambda: token_contract.functions.totalSupply().call()
            )

            # Calculate lock percentage
            if total_supply == 0:
                return False, {}
                
            lock_percentage = (total_locked / total_supply) * 100
            min_lock_percent = TRADING['min_locked_percent']
            is_sufficiently_locked = lock_percentage >= min_lock_percent

            if locks_found:
                logging.info(
                    f"Lock check for {token_address}:\n"
                    f"Total locked: {total_locked:.2f} tokens\n"
                    f"Lock percentage: {lock_percentage:.2f}%\n"
                    f"Lock platforms: {', '.join(locks_found.keys())}"
                )
            else:
                logging.warning(f"No locks found for {token_address}")

            return is_sufficiently_locked, locks_found

        except Exception as e:
            logging.error(f"Error checking locks for {token_address}: {e}")
            return False, {}

    async def get_token_info(self, rpc_manager, token_address: str) -> Dict:
        """Get basic token information"""
        try:
            token_contract = self.get_token_contract(token_address)
            
            # Get basic info
            name = await rpc_manager.execute_with_retry(
                lambda: token_contract.functions.name().call()
            )
            symbol = await rpc_manager.execute_with_retry(
                lambda: token_contract.functions.symbol().call()
            )
            decimals = await rpc_manager.execute_with_retry(
                lambda: token_contract.functions.decimals().call()
            )
            total_supply = await rpc_manager.execute_with_retry(
                lambda: token_contract.functions.totalSupply().call()
            )

            info = {
                'name': name,
                'symbol': symbol,
                'decimals': decimals,
                'total_supply': total_supply / (10 ** decimals),
            }
            
            logging.info(f"Token info for {token_address}: {name} ({symbol})")
            return info
            
        except Exception as e:
            logging.error(f"Error getting token info for {token_address}: {e}")
            return {}

    async def check_liquidity_lock(self, rpc_manager: RPCManager, pair_address: str, token_address: str) -> dict:
        """Likvidlik qulflanganligini tekshirish"""
        try:
            # Lock platformlari
            is_locked = False
            lock_details = {}
            
            # Juftlik kontrakti
            pair_contract = self.get_pair_contract(pair_address)
            
            # Lock kontraktlarni tekshirish
            for platform, lock_address in LOCK_CONTRACTS.get(self.network, {}).items():
                try:
                    # Lock platformidagi balansni tekshirish
                    locked_balance = await rpc_manager.execute_with_retry(
                        lambda: pair_contract.functions.balanceOf(lock_address).call()
                    )
                    
                    if locked_balance > 0:
                        # Pair dagi umumiy tokenlar
                        total_lp = await rpc_manager.execute_with_retry(
                            lambda: pair_contract.functions.totalSupply().call()
                        )
                        
                        lock_percent = (locked_balance / total_lp) * 100
                        is_locked = True
                        lock_details[platform] = lock_percent
                        
                        # 80% dan yuqori bo'lsa yetarli
                        if lock_percent >= 80:
                            return {
                                'is_locked': True,
                                'lock_details': {platform: lock_percent}
                            }
                        
                except Exception as e:
                    logging.debug(f"Error checking {platform} lock: {e}")
                    continue
            
            return {
                'is_locked': is_locked,
                'lock_details': lock_details
            }
            
        except Exception as e:
            logging.debug(f"Error checking liquidity lock: {e}")
            return {
                'is_locked': False,
                'lock_details': {}
            }
    async def analyze_token(self, rpc_manager: RPCManager, token_address: str, confirmed_liquidity: float = None):
        """Token xavfsizligini tekshirish"""
        try:
            # Token kontraktini olish
            token_contract = self.get_token_contract(token_address)
            token_info = {}
            
            # Token ma'lumotlarini olish
            token_info['name'] = await rpc_manager.execute_with_retry(
                lambda: token_contract.functions.name().call()
            )
            token_info['symbol'] = await rpc_manager.execute_with_retry(
                lambda: token_contract.functions.symbol().call()
            )
            token_info['decimals'] = await rpc_manager.execute_with_retry(
                lambda: token_contract.functions.decimals().call()
            )
            token_info['total_supply'] = await rpc_manager.execute_with_retry(
                lambda: token_contract.functions.totalSupply().call()
            ) / (10 ** token_info['decimals'])
            
            logging.info(f"Token info for {token_address}: {token_info['name']} ({token_info['symbol']})")
            
            # Juftlik manzilini olish
            pair_address = await rpc_manager.execute_with_retry(
                lambda: self.factory_contract.functions.getPair(
                    token_address,
                    self.wtoken_address
                ).call()
            )
            
            if pair_address == "0x0000000000000000000000000000000000000000":
                return {
                    'success': False,
                    'message': "No pair found"
                }
            
            # Juftlik kontraktini olish
            pair_contract = self.get_pair_contract(pair_address)
            
            # Likvidlikni tekshirish
            reserves = await rpc_manager.execute_with_retry(
                lambda: pair_contract.functions.getReserves().call()
            )
            
            token0 = await rpc_manager.execute_with_retry(
                lambda: pair_contract.functions.token0().call()
            )
            
            if token0.lower() == token_address.lower():
                token_reserve, native_reserve = reserves[0], reserves[1]
            else:
                token_reserve, native_reserve = reserves[1], reserves[0]
                
            # Likvidlik miqdori
            token_liquidity = token_reserve / (10 ** token_info['decimals'])
            native_liquidity = rpc_manager.web3.from_wei(native_reserve, 'ether')
            
            # Tasdiqlangan likvidlik mavjud bo'lsa, uni ishlatish
            if confirmed_liquidity is not None:
                native_liquidity = confirmed_liquidity
            
            # Likvidlik yetarliligini tekshirish
            if native_liquidity < self.min_liquidity:
                logging.warning(
                    f"Insufficient liquidity for {token_address}:\n"
                    f"Current: {native_liquidity:.4f} {self.native_currency}\n"
                    f"Required: {self.min_liquidity} {self.native_currency}"
                )
                return {
                    'success': False,
                    'message': f"Insufficient liquidity (Minimum: {self.min_liquidity} {self.native_currency})"
                }

            # Lock larni tekshirish
            is_locked = await self.check_liquidity_lock(rpc_manager, pair_address, token_address)
            
            # Dastlabki narxni hisoblash
            initial_price = (native_reserve / (10 ** 18)) / (token_reserve / (10 ** token_info['decimals']))
            
            return {
                'success': True,
                'details': {
                    'token_info': token_info,
                    'has_liquidity': True,
                    'token_liquidity': token_liquidity,
                    'native_liquidity': native_liquidity,
                    'native_currency': self.native_currency,
                    'is_locked': is_locked['is_locked'],
                    'lock_details': is_locked['lock_details'],
                    'initial_price': initial_price
                }
            }
                
        except Exception as e:
            logging.error(f"Error analyzing token {token_address}: {e}")
            return {
                'success': False,
                'message': str(e)
            }

    async def get_token_price(self, rpc_manager, token_address: str) -> Optional[float]:
        """Get token price in network's native currency"""
        try:
            amounts = await rpc_manager.execute_with_retry(
                lambda: self.router_contract.functions.getAmountsOut(
                    self.web3.to_wei(1, 'ether'),
                    [token_address, self.wtoken_address]
                ).call()
            )
            return self.web3.from_wei(amounts[1], 'ether')
        except Exception as e:
            logging.error(f"Error getting price for {token_address}: {e}")
            return None

    def get_pair_created_topic(self):
        """Get PairCreated event topic"""
        keccak_hash = self.web3.keccak(text="PairCreated(address,address,address,uint256)").hex()
        return "0x" + keccak_hash if not keccak_hash.startswith("0x") else keccak_hash