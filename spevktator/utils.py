def get_count(db, sql, params) -> int:
    "get count for progress bar"
    return next(
        db.query(
            "with t as ({}) select count(*) as c from t".format(sql),
            params=dict(params),
        )
    )["c"]
