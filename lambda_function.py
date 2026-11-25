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


def process_event(cursor, event):
    event_type = event["type"]

    if event_type not in ("capsule.sealed", "capsule.opened"):
        raise ValueError("Unsupported event type")

    capsule_id = event["capsule_id"]
    event_id = event["event_id"]

    cursor.execute("""
        SELECT
            c.id,
            c.user_id,
            c.title,
            c.open_at,
            COALESCE(c.recipient_email, u.email)
        FROM capsules c
        JOIN users u ON u.id = c.user_id
        WHERE c.id = %s
    """, (capsule_id,))

    capsule = cursor.fetchone()

    if capsule is None:
        print(f"Capsule {capsule_id} no longer exists")
        return

    capsule_id, user_id, title, open_at, recipient = capsule

    if event_type == "capsule.sealed":
        message = (
            f'Capsule "{title}" was sealed for you '
            f'until {open_at}.'
        )
    else:
        message = f'Your capsule "{title}" is now open.'

    time.sleep(
        float(os.environ.get("MAIL_DELAY_SECONDS", "3"))
    )

    cursor.execute("""
        INSERT INTO notifications (
            capsule_id,
            user_id,
            recipient,
            message,
            event_id
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (event_id) DO NOTHING
    """, (
        capsule_id,
        user_id,
        recipient,
        message,
        event_id
    ))

    if cursor.rowcount == 1:
        print(f"Notification created: {event_id}")
    else:
        print(f"Duplicate ignored: {event_id}")


def lambda_handler(event, context):
    connection = connect_db()

    try:
        cursor = connection.cursor()

        for record in event["Records"]:
            payload = json.loads(record["body"])

            if "responsePayload" in payload:
                events = payload["responsePayload"]["events"]
            else:
                events = [payload]

            for item in events:
                process_event(cursor, item)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()