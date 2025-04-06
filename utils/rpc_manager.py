import asyncio
import logging
from web3 import Web3
from datetime import datetime, timedelta
from config.settings import RPC_URLS, RPC_ROTATE_DELAY

class RPCManager:
    def __init__(self, network: str, db_manager):
        self.network = network
        self.db_manager = db_manager
        self.rpc_urls = self._get_prioritized_rpcs()
        self.current_rpc_index = 0
        self.current_rpc = self.rpc_urls[self.current_rpc_index]
        self.web3 = None
        self.setup_web3()
        self.current_rpc_url = self.current_rpc

    def _get_prioritized_rpcs(self):
        """Ishlagan RPClarni birinchi o'ringa qo'yish"""
        try:
            # Oxirgi ishlagan RPClarni olish
            working_rpcs = self.db_manager.get_working_rpcs(self.network)
            
            # Barcha RPClarni birlashtirish
            all_rpcs = list(RPC_URLS[self.network])  # config dan
            prioritized_rpcs = []
            
            # 1. Ishlagan RPClarni birinchi qo'shish
            for rpc in working_rpcs:
                if rpc in all_rpcs:
                    prioritized_rpcs.append(rpc)
                    all_rpcs.remove(rpc)
            
            # 2. Qolgan RPClarni qo'shish
            prioritized_rpcs.extend(all_rpcs)
            
            logging.info(
                f"RPCs initialized for {self.network}. "
                f"Working: {len(working_rpcs)}, Total: {len(prioritized_rpcs)}"
            )
            
            return prioritized_rpcs
            
        except Exception as e:
            logging.error(f"Error prioritizing RPCs: {e}")
            return RPC_URLS[self.network]

    def setup_web3(self):
        """RPC ga ulanish"""
        for i, rpc in enumerate(self.rpc_urls):
            try:
                self.web3 = Web3(Web3.HTTPProvider(
                    rpc,
                    request_kwargs={
                        'timeout': 30,
                        'verify': True,
                        'headers': {
                            'User-Agent': 'Mozilla/5.0',
                            'Accept': 'application/json',
                            'Content-Type': 'application/json'
                        }
                    }
                ))
                
                # RPC ishlashini tekshirish
                block = self.web3.eth.block_number
                self.current_rpc_index = i
                self.current_rpc = rpc
                
                # Ishlagan RPC ni bazaga saqlash
                self.db_manager.save_working_rpc(
                    network=self.network,
                    rpc_url=rpc,
                    last_success=datetime.now()
                )
                
                logging.info(f"✅ Connected to {self.network} network: {rpc} (Block: {block:,})")
                return
                
            except Exception as e:
                logging.warning(f"❌ Failed to connect to RPC {rpc}: {e}")
                continue
                
        raise Exception(f"Failed to connect to any RPC on {self.network} network")

    async def rotate_rpc(self):
        """Yangi RPC ga o'tish"""
        await asyncio.sleep(RPC_ROTATE_DELAY)
        
        old_index = self.current_rpc_index
        attempt_count = 0
        max_attempts = len(self.rpc_urls)
        
        while attempt_count < max_attempts:
            try:
                new_index = (old_index + 1) % len(self.rpc_urls)
                new_rpc = self.rpc_urls[new_index]
                
                web3 = Web3(Web3.HTTPProvider(
                    new_rpc,
                    request_kwargs={
                        'timeout': 10,
                        'verify': True,
                        'headers': {
                            'User-Agent': 'Mozilla/5.0',
                            'Accept': 'application/json',
                            'Content-Type': 'application/json'
                        }
                    }
                ))
                
                # RPC ishlashini tekshirish
                block_number = web3.eth.block_number
                
                # Yangi RPC ni saqlash
                self.current_rpc_index = new_index
                self.current_rpc = new_rpc
                self.web3 = web3
                
                # Ishlagan RPC ni bazaga saqlash
                self.db_manager.save_working_rpc(
                    network=self.network,
                    rpc_url=new_rpc,
                    last_success=datetime.now()
                )
                
                logging.info(
                    f"✅ Yangi RPC ga o'tildi: {new_rpc} ({self.network})\n"
                    f"Block: {block_number:,}"
                )
                return True
                
            except Exception as e:
                error_str = str(e).lower()
                
                if "limit exceeded" in error_str or "too many requests" in error_str:
                    logging.warning(f"⚠️ RPC {new_rpc} limit exceeded xatosi: {e}")
                else:
                    logging.warning(f"❌ RPC {new_rpc} ishlamadi: {e}")
                    
                old_index = new_index
                attempt_count += 1
                await asyncio.sleep(RPC_ROTATE_DELAY)
        
        return False

    # RPCManager klassiga qo'shish kerak
    async def validate_and_rotate_rpc(self, network: str):
        """RPC URLlarni tekshirish va aylantirib o'tish"""
        try:
            # Barcha RPC URLlarni olish
            rpcs = RPC_URLS.get(network, [])
            
            for rpc_url in rpcs:
                try:
                    # RPC URLni tekshirish
                    test_web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 10}))
                    latest_block = test_web3.eth.block_number
                    
                    # Agar block raqamini olsa, RPC ishlaydi
                    if latest_block > 0:
                        # Ishlaydigan RPC URLni saqlash
                        self.db_manager.save_working_rpc(network, rpc_url, datetime.now())
                        return test_web3
                    
                except Exception as e:
                    logging.warning(f"RPC URL {rpc_url} ishlamadi: {e}")
                    # RPC URLni bazada statini yangilash
                    self.db_manager.update_rpc_status(network, rpc_url, False, datetime.now(), str(e))
            
            # Agar hech qanday RPC URL ishlamasa
            logging.error(f"Hech qanday RPC URL {network} uchun ishlamadi!")
            return None
        
        except Exception as e:
            logging.error(f"RPC validatsiyasida xatolik: {e}")
            return None

    async def get_web3_for_network(self, network: str):
        """Ishlaydigan Web3 instanceni olish"""
        try:
            # RPC URLlarni prioritet tartibida saralash
            prioritized_urls = [
                # Eng ishonchli va tez RPC URLlar
                "https://cloudflare-eth.com",
                "https://eth.llamarpc.com",
                "https://rpc.ankr.com/eth",
                "https://ethereum.publicnode.com",
                "https://1rpc.io/eth",
                "https://eth.drpc.org",
                
                # Qolgan RPC URLlar
                *[url for url in self.rpc_urls if url not in [
                    "https://cloudflare-eth.com",
                    "https://eth.llamarpc.com", 
                    "https://rpc.ankr.com/eth",
                    "https://eth-mainnet.public.blastapi.io"  # Bu URL ko'p xato bergan
                ]]
            ]

            # Xatolik soni va urinishlar uchun o'zgaruvchilar
            max_connection_attempts = 3
            connection_attempts = 0

            while connection_attempts < max_connection_attempts:
                for i, url in enumerate(prioritized_urls):
                    try:
                        # WebSocket va HTTP providerlarni tekshirish
                        provider_types = [
                            Web3.HTTPProvider(
                                url,
                                request_kwargs={
                                    'timeout': 20,  # Vaqtni qisqartirdik
                                    'verify': True,
                                    'headers': {
                                        'User-Agent': 'Mozilla/5.0',
                                        'Accept': 'application/json',
                                        'Content-Type': 'application/json'
                                    }
                                }
                            )
                        ]

                        for provider in provider_types:
                            try:
                                test_web3 = Web3(provider)
                                
                                # Web3 ulanishini tekshirish
                                block = test_web3.eth.block_number
                                
                                if block > 0:
                                    self.web3 = test_web3
                                    self.current_rpc_index = i
                                    self.current_rpc = url
                                    self.current_rpc_url = url

                                    # Ishlagan RPC ni bazaga saqlash
                                    self.db_manager.save_working_rpc(
                                        network=network,
                                        rpc_url=url,
                                        last_success=datetime.now()
                                    )

                                    logging.info(f"✅ Connected to {network} network: {url} (Block: {block:,})")
                                    return test_web3
                            
                            except Exception as e:
                                logging.warning(f"❌ Provider {provider} ishlamadi: {e}")
                    
                    except Exception as e:
                        logging.warning(f"❌ Failed to connect to RPC {url}: {e}")
                        
                        # RPC URLning statusini yangilash
                        self.db_manager.update_rpc_status(
                            network, 
                            url, 
                            False, 
                            datetime.now(), 
                            str(e)
                        )
                
                # Urinishlar soni oshganda kutish vaqtini oshirish
                connection_attempts += 1
                wait_time = min(connection_attempts * 10, 60)  # Maksimal 60 sekund
                logging.warning(f"Barcha RPC URLlar ishlamadi. {wait_time} soniya kutilmoqda...")
                await asyncio.sleep(wait_time)
            
            # Agar hech qanday RPC URL ishlamasa
            raise Exception(f"Hech qanday RPC URL {network} uchun ishlamadi!")
        
        except Exception as e:
            logging.error(f"RPC validatsiyasida xatolik: {e}")
            raise
    async def execute_with_retry(self, operation):
        """RPC so'rovlarini qayta urinish bilan bajarish"""
        max_retries = len(self.rpc_urls)
        retries = 0
        last_error = None
        
        # RPC xatoliklari
        connection_errors = [
            "no route to host",
            "connection refused",
            "connection reset",
            "connection failed",
            "connection error",
            "connection aborted",
            "max retries exceeded",
            "timeout",
            "limit exceeded",
            "invalid argument",
            "bad gateway",
            "gateway timeout",
            "service unavailable",
            "rate limit",
            "too many requests"
        ]
        
        while retries < max_retries:
            try:
                # Web3 provayderini tekshirish
                if not isinstance(self.web3.provider, Web3.HTTPProvider):
                    self.web3.provider = Web3.HTTPProvider(
                        self.rpc_urls[self.current_rpc_index],
                        request_kwargs={
                            'timeout': 30,
                            'verify': True,
                            'headers': {
                                'User-Agent': 'Mozilla/5.0',
                                'Accept': 'application/json',
                                'Content-Type': 'application/json'
                            }
                        }
                    )
                
                # Operatsiyani bajarish
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, operation),
                    timeout=30
                )
                
                # Hex formatni tekshirish
                if isinstance(result, str) and len(result) > 2:
                    if not result.startswith('0x'):
                        result = '0x' + result
                return result
                
            except asyncio.TimeoutError:
                last_error = "RPC so'rovi timeout bo'ldi"
                logging.warning(
                    f"⚠️ RPC timeout {self.network} tarmog'ida ({retries + 1}/{max_retries}):\n"
                    f"RPC: {self.rpc_urls[self.current_rpc_index]}"
                )
                await self.rotate_rpc()
                
            except Exception as e:
                last_error = str(e).lower()
                
                # Xatolik turini tekshirish
                is_connection_error = any(err in last_error for err in connection_errors)
                
                if is_connection_error:
                    if "rate limit" in last_error or "too many requests" in last_error:
                        logging.warning(
                            f"⚠️ RPC rate limit {self.network} tarmog'ida ({retries + 1}/{max_retries}):\n"
                            f"RPC: {self.rpc_urls[self.current_rpc_index]}"
                        )
                    else:
                        logging.warning(
                            f"❌ RPC ulanish xatosi {self.network} tarmog'ida ({retries + 1}/{max_retries}):\n"
                            f"RPC: {self.rpc_urls[self.current_rpc_index]}\n"
                            f"Xatolik: {e}"
                        )
                    
                    await self.rotate_rpc()
                    
                    delay = RPC_ROTATE_DELAY * (retries + 1)
                    logging.info(f"⏳ Keyingi urinishdan oldin {delay} sekund kutilmoqda...")
                    await asyncio.sleep(delay)
                    
                    retries += 1
                    continue
                else:
                    logging.error(f"❗ Kutilmagan xatolik {self.network} tarmog'ida: {e}")
                    raise
        
        raise Exception(
            f"❌ Barcha RPC urinishlari muvaffaqiyatsiz yakunlandi "
            f"{self.network} tarmog'ida {max_retries} urinishdan so'ng.\n"
            f"Oxirgi xatolik: {last_error}"
        )

