ARG OPENSEARCH_VERSION=2.18.0
FROM opensearchproject/opensearch:${OPENSEARCH_VERSION}

ARG IK_PLUGIN_VERSION=2.18.0

RUN /usr/share/opensearch/bin/opensearch-plugin install -b \
    https://get.infini.cloud/opensearch/analysis-ik/${IK_PLUGIN_VERSION}

USER root

RUN mkdir -p /usr/share/opensearch/config/analysis-ik/config
RUN mkdir -p /usr/share/opensearch/plugins/analysis-ik/config

COPY ik/IKAnalyzer.cfg.xml /usr/share/opensearch/config/analysis-ik/config/IKAnalyzer.cfg.xml
COPY ik/IKAnalyzer.cfg.xml /usr/share/opensearch/config/analysis-ik/IKAnalyzer.cfg.xml
COPY ik/custom.dic /usr/share/opensearch/config/analysis-ik/custom.dic
COPY ik/stopword.dic /usr/share/opensearch/config/analysis-ik/stopword.dic
COPY ik/custom.dic /usr/share/opensearch/config/analysis-ik/config/custom.dic
COPY ik/stopword.dic /usr/share/opensearch/config/analysis-ik/config/stopword.dic
COPY ik/IKAnalyzer.cfg.xml /usr/share/opensearch/plugins/analysis-ik/config/IKAnalyzer.cfg.xml
COPY ik/main.dic /usr/share/opensearch/plugins/analysis-ik/config/main.dic
COPY ik/custom.dic /usr/share/opensearch/plugins/analysis-ik/config/custom.dic
COPY ik/stopword.dic /usr/share/opensearch/plugins/analysis-ik/config/stopword.dic
COPY ik/quantifier.dic /usr/share/opensearch/plugins/analysis-ik/config/quantifier.dic
COPY ik/surname.dic /usr/share/opensearch/plugins/analysis-ik/config/surname.dic
COPY ik/suffix.dic /usr/share/opensearch/plugins/analysis-ik/config/suffix.dic
COPY ik/preposition.dic /usr/share/opensearch/plugins/analysis-ik/config/preposition.dic

RUN chown -R opensearch:opensearch \
    /usr/share/opensearch/config/analysis-ik \
    /usr/share/opensearch/plugins/analysis-ik/config \
    && chmod -R u=rwX,g=rX,o=rX \
    /usr/share/opensearch/config/analysis-ik \
    /usr/share/opensearch/plugins/analysis-ik/config

USER opensearch
