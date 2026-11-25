import os
import ssl

import pg8000.dbapi


def connect_db():
    return pg8000.dbapi.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT", "5432")),
        database=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        ssl_context=ssl.create_default_context(
            cafile=os.path.join(
                os.path.dirname(__file__),
                "global-bundle.pem"
            )
        ),
        timeout=5
    )


def lambda_handler(event, context):
    connection = connect_db()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            UPDATE capsules
            SET opened_at = NOW() AT TIME ZONE 'UTC'
            WHERE opened_at IS NULL
              AND open_at <= NOW() AT TIME ZONE 'UTC'
            RETURNING id
        """)

        opened = [
            {
                "version": 1,
                "type": "capsule.opened",
                "event_id": f"capsule.opened:{row[0]}",
                "capsule_id": row[0]
            }
            for row in cursor.fetchall()
        ]

        connection.commit()

        print(f"Opened capsules: {len(opened)}")

        return {
            "type": "capsule.opened",
            "opened_count": len(opened),
            "events": opened
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()