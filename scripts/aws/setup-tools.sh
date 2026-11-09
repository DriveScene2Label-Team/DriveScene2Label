#!/usr/bin/env bash
# GitHub's Ubuntu runner only. CloudShell already includes aws/kubectl/helm.
set -euo pipefail
python3 -m pip install -r scripts/aws/requirements.txt
if ! command -v session-manager-plugin >/dev/null; then
  curl --fail --silent --show-error --location https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb --output /tmp/ds2l-session-manager.deb
  sudo dpkg -i /tmp/ds2l-session-manager.deb
fi
tools_dir=$(mktemp -d /tmp/ds2l-tools.XXXXXX)
trap 'rm -rf "$tools_dir"' EXIT
kubectl_version=v1.37.1
curl --fail --silent --show-error --location "https://dl.k8s.io/release/$kubectl_version/bin/linux/amd64/kubectl" --output "$tools_dir/kubectl"
curl --fail --silent --show-error --location "https://dl.k8s.io/release/$kubectl_version/bin/linux/amd64/kubectl.sha256" --output "$tools_dir/kubectl.sha256"
printf '%s  %s\n' "$(cat "$tools_dir/kubectl.sha256")" "$tools_dir/kubectl" | sha256sum --check
sudo install -m 0755 "$tools_dir/kubectl" /usr/local/bin/kubectl
helm_version=v3.19.0
curl --fail --silent --show-error --location "https://get.helm.sh/helm-$helm_version-linux-amd64.tar.gz" --output "$tools_dir/helm.tar.gz"
curl --fail --silent --show-error --location "https://get.helm.sh/helm-$helm_version-linux-amd64.tar.gz.sha256sum" --output "$tools_dir/helm.sha256sum"
expected=$(cut -d ' ' -f 1 "$tools_dir/helm.sha256sum")
printf '%s  %s\n' "$expected" "$tools_dir/helm.tar.gz" | sha256sum --check
tar -xzf "$tools_dir/helm.tar.gz" -C "$tools_dir"
sudo install -m 0755 "$tools_dir/linux-amd64/helm" /usr/local/bin/helm
