"""bestpred-mcp: run the server over stdio for an agent on this computer, or over HTTP to host it."""

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='bestpred-mcp', description=__doc__)
    ap.add_argument('--http', action='store_true',
                    help='serve it hosted: /mcp plus its pages, no file paths, capped input, nothing kept ($PORT wins)')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8000)
    args = ap.parse_args(argv)
    from .server import build_server

    if args.http:
        import os

        import uvicorn

        from .hosted import hosted_app

        hosts = [h.strip() for h in os.environ.get('BESTPRED_ALLOWED_HOSTS', '').split(',') if h.strip()]
        uvicorn.run(hosted_app(hosts), host=args.host, port=int(os.environ.get('PORT', args.port)),
                    proxy_headers=True, forwarded_allow_ips='*')
    else:
        build_server(hosted=False).run(transport='stdio')
    return 0


if __name__ == '__main__':
    sys.exit(main())
