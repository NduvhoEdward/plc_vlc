import { DatabaseSync } from 'node:sqlite';
export function localD1() {
  const db = new DatabaseSync(':memory:');
  return {
    prepare(sql) {
      const wrap = values => ({
        bind: (...args) => wrap(args),
        first: async () => db.prepare(sql).get(...values) || null,
        all: async () => ({results: db.prepare(sql).all(...values)}),
        run: async () => ({meta: {changes: Number(db.prepare(sql).run(...values).changes)}}),
      });
      return wrap([]);
    },
    batch: async statements => Promise.all(statements.map(x => x.run())),
  };
}
