"""bestpred-mcp: run the server over stdio for an agent on this computer, or over HTTP to host it."""

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='bestpred-mcp', description=__doc__)
    ap.add_argument('--http', action='store_true', help='serve streamable HTTP (hosted: no file paths, capped input)')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8000)
    args = ap.parse_args(argv)
    from .server import build_server

    if args.http:
        build_server(hosted=True).run(transport='streamable-http', host=args.host, port=args.port, json_response=True,
                                      stateless_http=True)
    else:
        build_server(hosted=False).run(transport='stdio')
    return 0


if __name__ == '__main__':
    sys.exit(main())
