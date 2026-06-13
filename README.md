# Family Tree Generator

## Usage

```sh
uv run main.py example.yaml
```

## Configuration

All family configuration is stored in a `.yaml` file.

### People

Each person can have a `name` and `secondaryName`. Other properties are ignored
(e.g. `previousName`).

```yaml
ElizabethII:
  name: Queen Elizabeth II
```

### Relationships

Relationships specify parents and children. `current` optionally indicates
whether the relationship is current.

```yaml
- partners:
    - ElizabethII
    - Philip
  children:
    - CharlesIII
    - Anne
    - AndrewMountbattenWindsor
    - Edward
```

### Config

Config allows specifying an `origin` from which the family tree is built.
Use `skipExpansion` for nodes that should appear in the tree but should not be
expanded further. Use `skipVisit` for nodes that should be omitted from the tree
entirely.

```yaml
config:
  origin: ElizabethII
  skipExpansion:
    - AndrewMountbattenWindsor
  skipVisit: []
```
