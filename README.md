<!-- badges -->

# ELVA Neovim Real-time Collaboration Plugin


## Roadmap

### Functionality

- [ ] bidirectional text sync
- [ ] bidirectional awareness sync
- [ ] efficient text delta passing between Neovim and plugin
- [ ] session management (grouping of documents)


### UI

- [ ] `ElvaConnect` command to connect to a document or session on a host
- [ ] `ElvaDisconnect` command to disconnect
- [ ] `ElvaServe` command to host a document or session
- [ ] `ElvaConfig` command to manage plugin options
- [ ] visualization of the current status (document, connection, peers)


### Compatibility

- [ ] ELVA editor app
- [ ] ELVA Emacs plugin `elva.el`
- [ ] Visual Studio Code


## Development

- environment setup

  ```sh
  uv venv
  ```

- pre-commit git hooks for compliance with code style

  ```sh
  prek install --config prek.yml
  ```

- testing

  ```sh
  pytest
  ```

- code coverage

  ```sh
  coverage run -m pytest
  ```
