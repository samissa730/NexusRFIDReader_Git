FROM smallstep/step-ca:latest

# Use root only to ensure permissions are correct if needed,
# but the base image usually handles /home/step/ well.
USER root
RUN mkdir -p /home/step/config /home/step/secrets /home/step/certs /home/step/db && \
    chown -R step:step /home/step

USER step

# Copy configuration and certificates
COPY --chown=step:step ./ca.json /home/step/config/
COPY --chown=step:step ./password /home/step/secrets/
COPY --chown=step:step ./certs/ /home/step/certs/

# Note: The database (/home/step/db) should ideally be a Docker Volume
# so your certificates/history aren't lost if the container is deleted.