import asyncio
import time

from route_ticket import route_ticket

# a handful of realistic tickets, distinct from eval_dataset.py, to avoid
# mixing timing runs with anything used for accuracy measurement
TIMING_TICKETS = [
    "My order still hasn't arrived and it's been over a week since it shipped.",
    "I was charged twice for my last purchase, can you refund the extra charge?",
    "Does the trail-runner backpack come in a 30L size?",
    "The app crashes every time I try to view my order history.",
    "I received the wrong color of the jacket I ordered.",
]


async def run_benchmark():
    timings = []
    for text in TIMING_TICKETS:
        start = time.perf_counter()
        await route_ticket(text)
        elapsed = time.perf_counter() - start
        timings.append(elapsed)
        print(f"{elapsed:.2f}s  - \"{text[:60]}\"")

    avg = sum(timings) / len(timings)
    print(f"\nAverage AI routing time: {avg:.2f}s over {len(timings)} tickets")
    return avg


if __name__ == "__main__":
    asyncio.run(run_benchmark())
