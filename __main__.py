from concurrent.futures import ProcessPoolExecutor, wait
from functools import partial
import pyximport
import numpy

pyximport.install(language_level=3, reload_support=True, setup_args={"include_dirs": numpy.get_include()})

import src.bot as bot

if __name__ == "__main__":
    shard_count = 5
    processes = []

    with ProcessPoolExecutor() as ppool:
        for shard_id in range(shard_count):
            processes.append(ppool.submit(partial(bot.run, shard_id, shard_count)))

        try:
            wait(processes)
        except KeyboardInterrupt:
            ppool.shutdown()
