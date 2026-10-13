"""Entry point: load cached state and the saved cookie, start refreshing, serve."""

from patreonfeed import config, session, store, web

if __name__ == "__main__":
    store.load_cache()
    session.load_saved()
    store.start_refresher()
    print(f"listening on :{config.PORT} for {len(config.FEEDS)} feeds", flush=True)
    web.serve(config.PORT)
