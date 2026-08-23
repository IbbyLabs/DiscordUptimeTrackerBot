FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Catalogues are committed as .po and gettext reads .mo, so they are compiled
# here rather than checked in — an image cannot then carry a stale one. The
# guard skips cleanly while no language has been translated; a real compile
# failure still fails the build.
RUN if find locales -name '*.po' | grep -q .; then pybabel compile -d locales; fi

CMD ["python", "bot.py"]
