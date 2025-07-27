FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies required for WeasyPrint, Pillow, and document processing
RUN dnf update -y && \
    dnf install -y tar xz gcc make pkgconfig \
    cairo cairo-devel \
    pango pango-devel \
    gdk-pixbuf2 gdk-pixbuf2-devel \
    gobject-introspection gobject-introspection-devel \
    libffi-devel \
    harfbuzz harfbuzz-devel \
    fontconfig fontconfig-devel \
    freetype freetype-devel \
    libpng-devel \
    zlib-devel && \
    dnf clean all && \
    rm -rf /var/cache/dnf

# Set environment variables for library paths
ENV LD_LIBRARY_PATH=/var/lang/lib:/lib64:/usr/lib64:/opt/lib
ENV PYTHONPATH=/var/task
ENV FONTCONFIG_PATH=/etc/fonts
ENV XDG_DATA_DIRS=/usr/share

# Install fonts
RUN dnf install -y urw-fonts && \
    fc-cache -fv && \
    dnf clean all

# Copy requirements file
COPY requirements.txt ${LAMBDA_TASK_ROOT}/

# Upgrade pip and install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy application files
COPY . ${LAMBDA_TASK_ROOT}/

# Test critical imports
RUN python -c "from weasyprint import HTML; from fastapi import FastAPI; from mangum import Mangum; print('Key imports successful')"

# Set the Lambda handler
CMD [ "main.handler" ]