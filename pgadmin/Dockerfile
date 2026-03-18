FROM dpage/pgadmin4:latest AS prod

USER root
COPY boot.sh /pgadmin4/boot.sh
RUN chmod +x /pgadmin4/boot.sh && chown 5050:5050 /pgadmin4/boot.sh
USER 5050

ENTRYPOINT ["/pgadmin4/boot.sh"]