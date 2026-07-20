def get_replay_expiry(replay_date, expiries):
    for expiry in sorted(expiries):
        if expiry >= replay_date:
            return expiry

    raise Exception("No valid expiry found")