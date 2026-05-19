.PHONY: *

mm:
	uv run manage.py makemigrations
	uv run manage.py migrate

cronjobs:
	uv run manage.py crontab remove
	uv run manage.py crontab add
	uv run manage.py crontab show

twrun:
	uv run manage.py tailwind start

task:
	uv run celery -A idiotship worker -l info -P solo

run:
	uv run manage.py runserver

csu:
	uv run manage.py createsuperuser

freeze:
	pip freeze > requirements.txt

ruff:
	ruff check

ngrun:
	uv run manage.py runserver 0.0.0.0:8000

test:
	@make ruff
	uv run manage.py test

collectstatic:
	uv run manage.py collectstatic --noinput

ireq:
	uv sync

mcheck:
	uv run manage.py check


clean:
	rm ./*/migrations/00*.py
	rm ./*/__pycache__/*
	rm ./*/migrations/__pycache__/*.pyc

cleandb:
	rm -rf db.sqlite3
	@make clean
	@make mm
	@make csu

delete_old_bulk_order_files:
	uv run manage.py delete_old_bulk_order_files

delete_old_barcode_or_non_required:
	uv run manage.py delete_old_barcode_or_non_required

sys:
	sudo systemctl reload nginx
	sudo systemctl restart redis-server
	sudo systemctl restart celery-worker
	sudo systemctl restart gunicorn

sync_static:
	aws s3 sync /home/ubuntu/project/idiotship/static_prod/ s3://shipee-static-media-storage/static/
	aws s3 sync /home/ubuntu/project/idiotship/media/ s3://shipee-static-media-storage/media/

ready:
	git pull
	@make ireq
	@make mm
	@make cronjobs
	@make delete_old_bulk_order_files
	@make delete_old_barcode_or_non_required
	uv run manage.py tailwind build
	@make collectstatic
	@make sys

setup:
	uv sync
	@make mm
	@make csu
	@make cronjobs
	