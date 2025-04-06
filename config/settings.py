from dotenv import load_dotenv
import os
from pathlib import Path
from web3 import Web3
# Load environment variables
load_dotenv()

# Get active networks from env
ACTIVE_NETWORKS = os.getenv('ACTIVE_NETWORKS', 'bsc').split(',')

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Database configuration
DB_PATH = os.path.join(BASE_DIR, 'database.db')

# RPC URLs
RPC_URLS = {
    'bsc': [
        "https://bsc.publicnode.com",
        "https://1rpc.io/bnb",
    ],
    'ethereum': [
        "https://eth.llamarpc.com",
        "https://ethereum.publicnode.com",
        "https://1rpc.io/eth",
        "https://rpc.ankr.com/eth",
        "https://eth.drpc.org",
        "https://eth.meowrpc.com",
        "https://rpc.flashbots.net",
        "https://mainnet-nethermind.blockscout.com",
        "https://rpc.builder0x69.io",
        "https://rpc.ankr.com/eth",
        "https://eth-rpc.gateway.pokt.network",
        "https://main-light.eth.linkpool.io",
        "https://eth-mainnet.public.blastapi.io",
        "https://api.securerpc.com/v1",
        "https://cloudflare-eth.com",
        "https://rpc.payload.de",
        "https://nodes.mewapi.io/rpc/eth",
        "https://main-rpc.linkpool.io",
        "https://eth-mainnet.gateway.pokt.network/v1/5f3453978e354ab992c4da79",
        "https://mainnet.eth.cloud.ava.do",
        "https://ethereumnodelight.app.runonflux.io",
        
    ],
    'polygon': [
        "https://polygon-rpc.com",
        "https://polygon.llamarpc.com",
        "https://1rpc.io/matic",
        "https://polygon.blockpi.network/v1/rpc/public",
        "https://polygon-mainnet.public.blastapi.io",
        "https://rpc-mainnet.maticvigil.com",
        "https://rpc-mainnet.matic.quiknode.pro",
    ]
}

NETWORKS = {
    'bsc': {
        'id': 56,
        'currency': 'BNB',
        'min_liquidity': float(os.getenv('MIN_LIQUIDITY_BNB', '50.0')),
        'dexes': {
            'pancakeswap': {
                'name': 'PancakeSwap',
                'factory': '0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73',
                'router': '0x10ED43C718714eb63d5aA57B78B54704E256024E',
                'wtoken': '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',  # WBNB
            },
            'biswap': {
                'name': 'Biswap',
                'factory': '0x858E3312ed3A876947EA49d572A7C42DE08af7EE',
                'router': '0x3a6d8cA21D1CF76F653A67577FA0D27453350dD8',
                'wtoken': '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',  # WBNB
            }
        }
    },
    'ethereum': {
        'id': 1,
        'currency': 'ETH',
        'min_liquidity': float(os.getenv('MIN_LIQUIDITY_ETH', '10.0')),
        'dexes': {
            'uniswap': {
                'name': 'Uniswap V2',
                'factory': '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f',
                'router': '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D',
                'wtoken': '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',  # WETH
            }
        }
    },
    'polygon': {
        'id': 137,
        'currency': 'MATIC',
        'min_liquidity': float(os.getenv('MIN_LIQUIDITY_MATIC', '1000.0')),
        'dexes': {
            'quickswap': {
                'name': 'QuickSwap',
                'factory': '0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32',
                'router': '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff',
                'wtoken': '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270',  # WMATIC
            }
        }
    }
}
# Monitoring parameters
BLOCKS_TO_CHECK = int(os.getenv('BLOCKS_TO_CHECK', '10'))

LOCK_CONTRACTS = {
    'bsc': {
        'unicrypt': Web3.to_checksum_address('0xC765bddB93b0D1c1A88282BA0fa6B2d00E3e0c83'),
        'pinksale': Web3.to_checksum_address('0x407993575c91ce7643a4d4cCACc9A98c36eE1BBE'),
        'dxsale': Web3.to_checksum_address('0x86d8e818E53C3C272E8c9c10E579765102208289'), 
        'mudra': Web3.to_checksum_address('0x0b5f57108071b58944ab899f21c515d94a10e416')
    },
    'ethereum': {
        'unicrypt': Web3.to_checksum_address('0x663A5C229c09b049E36dCc11a9B0d4a8Eb9db214'),
        'team.finance': Web3.to_checksum_address('0xE2fE530C047f2d85298b07D9333C05737f1435fB')
    }
}

# Trading sozlamalari
TRADING = {
    # Asosiy sozlamalar
    'enabled': True,  # Trading funksiyasini yoqish
    'private_key': os.getenv('PRIVATE_KEY'),  # Hamyon private key
    'networks': ACTIVE_NETWORKS,  # Active networklarda trading qilish
    
    # Trade miqdorlari va strategiyasi
    'buy_strategy': {
        'locked_liquidity': {
            'enabled': True,
            'amount_percent': 10,  # Balansning 10%
            'min_lock_percent': 80,  # Minimal lock foizi
            'take_profit': [
                {'multiplier': 3, 'percent': 33},  # 3x da 33% sotish
                {'multiplier': 10, 'percent': 50}, # 10x da 50% sotish
                {'multiplier': 50, 'percent': 100} # 50x da qolganini sotish
            ]
        },
        'unlocked_liquidity': {
            'enabled': True,
            'amount_usd': 1,  # $1 lik
            'take_profit': [
                {'multiplier': 2, 'percent': 50},  # 2x da 50% sotish
                {'multiplier': 5, 'percent': 50},  # 5x da 50% sotish
                {'multiplier': 10, 'percent': 50}, # 10x da 50% sotish
                {'multiplier': 20, 'percent': 100} # 20x da qolganini sotish
            ]
        }
    },
    
    # Xavfsizlik parametrlari
    'max_slippage': float(os.getenv('MAX_SLIPPAGE', '3')),
    'gas_multiplier': 1.1,  # Gas narxini oshirish (x1.1)
    'min_liquidity_bnb': float(os.getenv('MIN_LIQUIDITY_BNB', '50.0')),
    'min_locked_percent': float(os.getenv('MIN_LOCKED_PERCENT', '50')),
    'max_buy_tax': float(os.getenv('MAX_BUY_TAX', '10')),
    'max_sell_tax': float(os.getenv('MAX_SELL_TAX', '10')),
    
    # Auto-sell parametrlari
    'auto_sell': {
        'enabled': True,
        'take_profit': [  # Take-profit darajalari
            {'multiplier': 2, 'percent': 50},  # 2x da 50% sotish
            {'multiplier': 3, 'percent': 25},  # 3x da 25% sotish
            {'multiplier': 4, 'percent': 25}   # 4x da qolgan 25% ni sotish
        ],
        'stop_loss': 0.8,  # Stop-loss (-20%)
        'trailing_stop': {
            'enabled': True,
            'percent': 20  # 20% pastga tushsa sotish
        }
    },
    
    # Xavfsizlik tekshiruvlari
    'check_honeypot': True,
    'check_contract': True,
    'check_team_tokens': True,
    'check_lp_lock': True
}

# Vaqt intervallari (sekundlar)
POLLING_INTERVAL = 15       # Yangi juftliklarni tekshirish vaqti
PRICE_CHECK_INTERVAL = 1   # Narxni tekshirish vaqti
RPC_ROTATE_DELAY = 3       # RPC almashish vaqti
RPC_ERROR_SLEEP = 1       # RPC xatoligida kutish vaqti
MONITORING_DURATION = 180   # Token monitoring vaqti (3 daqiqa)
INITIAL_PRICE_MONITOR = 300 # Dastlabki narx monitoring vaqti (5 daqiqa)

# Narx targetlari
PRICE_TARGETS = [2, 4, 10, 16]

# Ma'lumotlar bazasi
DB_NAME = 'tokens.db'

# Logging
LOG_FILE = 'token_monitor.log'
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'

# Blacklist
BLACKLIST = {
    'tokens': [],     # Blacklist qilingan tokenlar
    'contracts': [],  # Blacklist qilingan kontraktlar
    'deployers': []   # Blacklist qilingan deployer addresslar
}

# Whitelist
WHITELIST = {
    'tokens': [],     # Whitelist qilingan tokenlar
    'contracts': [],  # Whitelist qilingan kontraktlar
    'deployers': []   # Whitelist qilingan deployer addresslar
}