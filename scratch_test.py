import httpx
import asyncio

async def main():
    payload = {
        "user_id": "test",
        "query": "Calculate 125 * 42",
        "input_type": "text"
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post("http://localhost:8000/api/v1/query", json=payload, timeout=30.0)
            print(resp.status_code)
            print(resp.json())
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
