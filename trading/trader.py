import logging
from web3 import Web3
from eth_account import Account
from eth_utils import to_checksum_address
from typing import Dict, Optional, List
from decimal import Decimal
import time
from dotenv import load_dotenv
import os
class TokenTrader:
    def __init__(self, private_key: str, network_settings: Dict):
        """Initialize trader with private key and network settings"""
        try:
            # Load environment variables
            load_dotenv()
            self.min_buy_amount_usd = float(os.getenv('MIN_BUY_AMOUNT_USD', '1'))
            self.balance_percent = float(os.getenv('BALANCE_PERCENT', '10'))
            
            # Private key validation and setup
            if private_key:
                private_key = private_key.strip()
                if private_key.startswith('0x'):
                    private_key = private_key[2:]
                    
            if not private_key or len(private_key) != 64:
                raise ValueError(f"Invalid private key length or format")
            
            # Create account
            private_key_bytes = bytes.fromhex(private_key)
            self.private_key = f"0x{private_key}"
            self.account = Account.from_key(self.private_key)
            self.wallet_address = to_checksum_address(self.account.address)
            
            # Save network settings
            self.network_settings = network_settings
            
            logging.info(
                f"Wallet initialized successfully.\n"
                f"Address: {self.wallet_address}\n"
                f"Network: {self.network_settings['currency']}\n"
                f"Min Buy Amount: ${self.min_buy_amount_usd}\n"
                f"Balance Percent: {self.balance_percent}%"
            )
            
        except Exception as e:
            logging.error(f"Wallet initialization error: {e}")
            raise

    async def calculate_buy_amount(self, web3: Web3, is_locked: bool, is_test: bool = False) -> tuple:
        """
        Sotib olish miqdorini hisoblash
        
        :param web3: Web3 instance
        :param is_locked: Likvidlik qulflangan yoki yo'q
        :param is_test: Test rejimi yoki haqiqiy savdo
        :return: Sotib olish miqdori va strategiya
        """
        try:
            # Native valyuta nomini aniqlash
            native_currency = self.network_settings['currency'].lower()
            
            # Test rejimi
            if is_test:
                # Test uchun minimal miqdor (bnb va eth uchun bir xil)
                test_amount = 0.0006
                return test_amount, 'test_mode'
            
            # Haqiqiy savdo uchun
            # Balansdan qat'i nazar bir xil miqdor
            amount_native = 0.003 if native_currency == 'bnb' else 0.0005
            strategy = 'trade_strategy'
            
            # Minimal miqdorni tekshirish
            amount_native = max(amount_native, 0.0005)
            
            return amount_native, strategy
        
        except Exception as e:
            logging.error(f"Error calculating buy amount: {e}")
            return 0, None


    def get_take_profit_levels(self, strategy: str) -> List[dict]:
        """Get take profit levels based on strategy"""
        from config.settings import TRADING
        
        if strategy == 'locked_liquidity':
            return TRADING['buy_strategy']['locked_liquidity']['take_profit']
        else:
            return TRADING['buy_strategy']['unlocked_liquidity']['take_profit']

    async def buy_token(self, web3: Web3, token_address: str, router_contract, is_locked: bool, buy_amount: float = None) -> Dict:
        """Buy token with amount based on strategy or custom amount"""
        try:
            # Sotib olish miqdorini hisoblash
            if buy_amount is None:
                amount_bnb, strategy = await self.calculate_buy_amount(web3, is_locked)
            else:
                amount_bnb = buy_amount  # Foydalanuvchi bergan miqdor
                strategy = 'trade_strategy'

            # Test rejimida minimal miqdorni belgilash
            native_currency = self.network_settings['currency'].lower()
            if amount_bnb == 0:
                amount_bnb = 0.0006  # Test uchun bir xil miqdor

            if amount_bnb <= 0:
                return {
                    'success': False,
                    'message': 'Invalid buy amount'
                }
            
            amount_in = web3.to_wei(amount_bnb, 'ether')
            
            # Get wrapped token address (WETH/WBNB)
            wtoken_address = self.network_settings['wtoken']
            
            # Get minimum output amount
            try:
                amounts = router_contract.functions.getAmountsOut(
                    amount_in,
                    [wtoken_address, token_address]
                ).call()
            except Exception as e:
                return {
                    'success': False,
                    'message': f'Error calculating amounts: {str(e)}'
                }
            
            # Slippage va minimal output miqdorini hisoblash
            min_output = int(amounts[1] * 0.97)  # 3% slippage
            
            # Transaction parametrlari
            try:
                gas_price = web3.eth.gas_price
                gas_limit = 500000  # Standart gas limit
                
                # Balansni tekshirish
                balance = web3.eth.get_balance(self.wallet_address)
                tx_cost = gas_price * gas_limit + amount_in
                
                if balance < tx_cost:
                    return {
                        'success': False,
                        'message': f'Insufficient balance. Required: {web3.from_wei(tx_cost, "ether")} {native_currency}, Current: {web3.from_wei(balance, "ether")} {native_currency}'
                    }
                
                tx_params = {
                    'from': self.wallet_address,
                    'value': amount_in,
                    'gas': gas_limit,
                    'gasPrice': int(gas_price * 1.1),  # 10% gas price oshirish
                    'nonce': web3.eth.get_transaction_count(self.wallet_address)
                }
                
                # Build transaction
                tx = router_contract.functions.swapExactETHForTokens(
                    min_output,
                    [wtoken_address, token_address],
                    self.wallet_address,
                    int(time.time() + 60)
                ).build_transaction(tx_params)
                
                # Sign and send
                signed_tx = web3.eth.account.sign_transaction(tx, self.private_key)
                tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
                
                # Wait for confirmation
                receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
                
                if receipt['status'] == 1:
                    take_profit_levels = self.get_take_profit_levels(strategy)
                    
                    logging.info(
                        f"✅ Successfully bought {amounts[1]} tokens\n"
                        f"Amount spent: {amount_bnb} {self.network_settings['currency']}\n"
                        f"Strategy: {strategy}\n"
                        f"TX: {tx_hash.hex()}"
                    )
                    
                    return {
                        'success': True,
                        'tx_hash': tx_hash.hex(),
                        'amount_in': amount_bnb,
                        'token_amount': amounts[1],
                        'strategy': strategy,
                        'take_profit_levels': take_profit_levels
                    }
                else:
                    return {
                        'success': False,
                        'message': 'Transaction failed'
                    }
                
            except Exception as e:
                error_msg = str(e)
                logging.error(f"Error buying token: {error_msg}")
                return {
                    'success': False,
                    'message': f'Buy error: {error_msg}'
                }
                        
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error buying token: {error_msg}")
            return {
                'success': False,
                'message': f'Buy error: {error_msg}'
            }

    async def sell_token(self, web3: Web3, token_address: str, router_contract, amount: int, test_mode: bool = False) -> Dict:
        """Execute token sell"""
        try:
            # Get wrapped token address (WETH/WBNB)
            wtoken_address = self.network_settings['wtoken']
            
            # Get minimum output amount
            try:
                amounts = router_contract.functions.getAmountsOut(
                    amount,
                    [token_address, wtoken_address]
                ).call()
            except Exception as e:
                return {
                    'success': False,
                    'message': f'Error calculating sell amounts: {str(e)}'
                }
            
            min_output = int(amounts[1] * 0.97)  # 3% slippage
            
            # Test rejimida token transfer imkoniyatini tekshirish
            if test_mode:
                # Test rejimida barcha tokenlarni sotish
                amounts[1] = amount
                
                return {
                    'success': True,
                    'amount_out': amounts[1] / (10 ** 18),  # Wei dan Ether ga
                    'message': 'Test sell successful'
                }
            
            # Haqiqiy sotish operatsiyasi
            tx = router_contract.functions.swapExactTokensForETH(
                amount,
                min_output,
                [token_address, wtoken_address],
                self.wallet_address,
                int(time.time() + 60)
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 500000,
                'gasPrice': int(web3.eth.gas_price * 1.1),
                'nonce': web3.eth.get_transaction_count(self.wallet_address)
            })
            
            # Sign and send
            signed_tx = web3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            # Wait for confirmation
            receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt['status'] == 1:
                amount_out = web3.from_wei(amounts[1], 'ether')
                logging.info(
                    f"💰 Successfully sold {amount} tokens\n"
                    f"Received: {amount_out} {self.network_settings['currency']}\n"
                    f"TX: {tx_hash.hex()}"
                )
                
                return {
                    'success': True,
                    'tx_hash': tx_hash.hex(),
                    'amount_sold': amount,
                    'amount_out': amount_out
                }
            else:
                return {
                    'success': False,
                    'message': 'Sell transaction failed'
                }
            
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error selling token: {error_msg}")
            return {
                'success': False,
                'message': f'Sell error: {error_msg}'
            }